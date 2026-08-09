# app/services/audit_service.py
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

# First row in the chain has no real predecessor -- a fixed all-zero
# "hash" plays the same role a null parent commit does in git, or a
# genesis block's prev-hash in a blockchain: an explicit, unambiguous
# value rather than NULL, so every row's prev_hash is always comparable
# with `==` during verification.
GENESIS_HASH = "0" * 64

# Arbitrary fixed key for a Postgres session-level advisory lock, scoped to
# the writing transaction (pg_advisory_xact_lock auto-releases on commit or
# rollback). Without this, two concurrent compatibility checks could both
# read the same "last row" as their prev_hash and each append a row
# chained from it -- two valid-looking rows that fork the chain instead of
# extending it in one linear order, which quietly defeats verification's
# ability to prove there's a single, complete history.
_AUDIT_CHAIN_LOCK_KEY = 8817364529


def compute_audit_hash(
    prev_hash: str,
    doctor_id: uuid.UUID,
    patient_id: Optional[uuid.UUID],
    donor_id: Optional[uuid.UUID],
    action: str,
    created_at: datetime,
    details: Optional[dict],
    row_id: uuid.UUID,
) -> str:
    """Deterministic sha256 over one audit row's fields, chained to the
    previous row's hash. patient_id/donor_id are folded in alongside the
    (prev_hash, doctor_id, action, timestamp, details) the row is
    conceptually keyed on, so a retroactive edit that swaps which
    patient/donor a log entry points at also breaks the chain.

    row_id (added 2026-08-09, review #2 bug 16) is the row's own primary
    key -- without it, an attacker with UPDATE access could swap two rows'
    `id` values (or reassign a row's id to some other value) without
    touching any hashed field, and verification would still pass, since
    nothing tied a row's hash to which row it actually was.
    UUIDPrimaryKeyMixin generates `id` client-side (default=uuid.uuid4, not
    a server default), so create_audit_log can know it up front and hash
    it in the same pass rather than needing a flush-then-rehash.

    json.dumps(..., sort_keys=True) keeps `details` deterministic regardless
    of the dict's original key insertion order -- callers build that dict
    fresh every time, so insertion order isn't meaningful and can't be
    trusted to match between the write and a later verification pass.
    """
    payload = "|".join(
        [
            prev_hash,
            str(doctor_id),
            str(patient_id) if patient_id is not None else "",
            str(donor_id) if donor_id is not None else "",
            action,
            created_at.isoformat(),
            json.dumps(details, sort_keys=True, default=str) if details is not None else "null",
            str(row_id),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _get_last_audit_hash(db: AsyncSession) -> str:
    # Ordered by seq, not created_at: seq is a monotonic BIGSERIAL-style
    # counter immune to clock steps (see AuditLog.seq's docstring / review
    # #2 bug 2) -- created_at can go backwards across an NTP correction,
    # which used to make this pick the wrong "last" row and fork the chain.
    result = await db.execute(select(AuditLog.hash).order_by(AuditLog.seq.desc()).limit(1))
    last_hash = result.scalar_one_or_none()
    return last_hash if last_hash is not None else GENESIS_HASH


async def create_audit_log(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    action: str,
    patient_id: Optional[uuid.UUID] = None,
    donor_id: Optional[uuid.UUID] = None,
    details: Optional[dict] = None,
    commit: bool = True,
) -> AuditLog:
    """commit=False lets a caller that's already writing other rows in this
    transaction (see match_report_service.create_match_report's commit
    param) fold the audit entry into that same commit, so a crash between
    the two can't leave one without the other. The advisory lock below is
    still acquired per-call and held until whichever commit actually runs,
    so the chain stays correctly serialized either way.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUDIT_CHAIN_LOCK_KEY})

    created_at = datetime.now(timezone.utc)
    row_id = uuid.uuid4()  # generated up front so it can be hashed -- see compute_audit_hash's docstring
    prev_hash = await _get_last_audit_hash(db)
    row_hash = compute_audit_hash(
        prev_hash, doctor_id, patient_id, donor_id, action, created_at, details, row_id
    )

    log_entry = AuditLog(
        id=row_id,
        doctor_id=doctor_id,
        action=action,
        patient_id=patient_id,
        donor_id=donor_id,
        details=details,
        created_at=created_at,
        prev_hash=prev_hash,
        hash=row_hash,
    )
    db.add(log_entry)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(log_entry)

    return log_entry


async def get_audit_logs(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
) -> tuple[list[AuditLog], int]:
    """Returns (rows, total_count) for the given page/filters, newest first.

    total_count is the count across ALL matching rows (ignoring limit/offset),
    so the frontend can render "Page 2 of 14" style pagination.
    """
    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if doctor_id is not None:
        query = query.where(AuditLog.doctor_id == doctor_id)
        count_query = count_query.where(AuditLog.doctor_id == doctor_id)

    if patient_id is not None:
        query = query.where(AuditLog.patient_id == patient_id)
        count_query = count_query.where(AuditLog.patient_id == patient_id)

    if action is not None:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    query = query.order_by(AuditLog.seq.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    rows = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total_count = total_result.scalar_one()

    return rows, total_count


@dataclass
class AuditChainVerification:
    is_valid: bool
    checked_count: int
    total_count: int
    first_broken_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None


async def verify_audit_chain(db: AsyncSession) -> AuditChainVerification:
    """Walks the whole table oldest-first and recomputes each row's hash
    from its stored fields, checking both that it matches the row's stored
    `hash` and that its `prev_hash` matches the preceding row's hash.

    This proves the table matches the sequence of create_audit_log() calls
    that originally produced it -- an UPDATE that alters any hashed field on
    row N changes what row N's hash *should* be without changing the stored
    value, so verification fails at N; a DELETE of row N leaves row N+1's
    prev_hash pointing at a hash no longer present (and now also a seq gap
    -- see the loop below), both of which fail here, whether the deleted
    row was in the middle or was the row this walk would otherwise have
    started from.
    What it still can't catch: someone deleting a *trailing* run of the
    most recent rows (the chain and its seq sequence that remain are both
    still internally consistent, just shorter -- there's nothing after the
    cut to notice a gap; closing this needs a write-side protection, e.g.
    revoking DELETE on this table from the application's own DB role, not
    something a read-time check can prove on its own), or someone with DB
    access recomputing and rewriting every row's hash *and* seq to match
    tampered content (this is tamper-evident against casual/accidental
    edits and ordinary application-level UPDATE/DELETE, not against an
    attacker with unrestricted write access to Postgres itself).
    """
    # populate_existing=True: a verification pass must reflect the row's
    # true current DB state even if this session already has a stale copy
    # of it identity-mapped from earlier in the same session (e.g. from the
    # create_audit_log call that originally wrote it) -- without this, an
    # UPDATE made through a separate raw-SQL statement on this same session
    # wouldn't be picked up here, since expire_on_commit=False (see
    # app/db/session.py) means commit() doesn't invalidate already-loaded
    # ORM objects on its own.
    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.seq.asc())
        .execution_options(populate_existing=True)
    )
    rows = list(result.scalars().all())

    expected_prev = GENESIS_HASH
    for checked_count, row in enumerate(rows, start=1):
        # seq is gap-free by construction (a real Postgres sequence, one
        # value per row ever inserted) -- checked_count (1, 2, 3, ...)
        # should equal row.seq exactly. A jump here (seq goes 1, 2, 4)
        # means row 3 was deleted from the *middle* of the chain: the
        # surviving rows can still look internally consistent on
        # prev_hash/hash alone (each still correctly points at its actual
        # predecessor), so this check catches what that one can't. See
        # review #2 bug 1 -- this still can't catch a deleted *trailing*
        # run of the newest rows (nothing after it to notice a gap); that
        # needs a write-side protection (e.g. revoking DELETE on this table
        # from the application's DB role), not something a read-time check
        # can prove.
        if row.seq != checked_count:
            return AuditChainVerification(
                is_valid=False,
                checked_count=checked_count,
                total_count=len(rows),
                first_broken_id=row.id,
                reason=(
                    f"seq gap detected: expected seq {checked_count}, found {row.seq} "
                    "-- a row appears to have been deleted from the middle of the chain"
                ),
            )

        if row.prev_hash != expected_prev:
            return AuditChainVerification(
                is_valid=False,
                checked_count=checked_count,
                total_count=len(rows),
                first_broken_id=row.id,
                reason="prev_hash does not match the preceding row's hash",
            )

        recomputed = compute_audit_hash(
            row.prev_hash, row.doctor_id, row.patient_id, row.donor_id,
            row.action, row.created_at, row.details, row.id,
        )
        if recomputed != row.hash:
            return AuditChainVerification(
                is_valid=False,
                checked_count=checked_count,
                total_count=len(rows),
                first_broken_id=row.id,
                reason="stored hash does not match a recomputed hash of this row's fields",
            )

        expected_prev = row.hash

    return AuditChainVerification(is_valid=True, checked_count=len(rows), total_count=len(rows))

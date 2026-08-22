# app/tests/integration/test_audit_service.py
"""Chain-building and verify_audit_chain behavior for the audit log hash
chain -- needs a real DB session and committed rows to hash and tamper
with. Pure compute_audit_hash tests live in
app/tests/unit/test_audit_service.py."""
import uuid

from sqlalchemy import select, text

from app.models.audit_log import AuditLog
from app.services.audit_service import (
    GENESIS_HASH,
    compute_audit_hash,
    create_audit_log,
    verify_audit_chain,
)


async def test_first_row_chains_from_genesis(db_session):
    entry = await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="first_action")

    assert entry.prev_hash == GENESIS_HASH
    assert entry.hash == compute_audit_hash(
        GENESIS_HASH, entry.doctor_id, None, None, "first_action", entry.created_at, None, entry.id
    )


async def test_second_row_chains_from_first(db_session):
    first = await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="first_action")
    second = await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="second_action")

    assert second.prev_hash == first.hash
    assert second.hash != first.hash


async def test_commit_false_defers_to_the_caller(db_session):
    entry = await create_audit_log(
        db_session, doctor_id=uuid.uuid4(), action="uncommitted_action", commit=False
    )
    # Flushed (has an id/hash) but not yet committed.
    assert entry.id is not None

    await db_session.rollback()

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "uncommitted_action")
    )
    assert result.scalar_one_or_none() is None


async def test_verify_audit_chain_passes_on_an_untouched_chain(db_session):
    await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="a", details={"x": 1})
    await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="b", details={"y": 2})
    await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="c")

    result = await verify_audit_chain(db_session)

    assert result.is_valid is True
    assert result.checked_count == 3
    assert result.total_count == 3
    assert result.first_broken_id is None


async def test_verify_audit_chain_detects_a_retroactive_update(db_session):
    await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="a")
    target = await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="b")
    await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="c")

    # Simulate exactly what the finding describes: an ordinary UPDATE against
    # the table, bypassing create_audit_log entirely -- the row's stored
    # `hash` is untouched, so it no longer matches a recomputed hash of its
    # (now-different) content.
    await db_session.execute(
        text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"), {"id": target.id}
    )
    await db_session.commit()

    result = await verify_audit_chain(db_session)

    assert result.is_valid is False
    assert result.first_broken_id == target.id
    assert result.checked_count == 2  # row 1 verified clean, row 2 (target) is where it broke
    assert result.total_count == 3


async def test_verify_audit_chain_detects_a_deleted_middle_row(db_session):
    await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="a")
    middle = await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="b")
    last = await create_audit_log(db_session, doctor_id=uuid.uuid4(), action="c")

    await db_session.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": middle.id})
    await db_session.commit()

    result = await verify_audit_chain(db_session)

    # `last`'s prev_hash still points at the now-missing middle row's hash,
    # which no longer matches the row now immediately before it.
    assert result.is_valid is False
    assert result.first_broken_id == last.id

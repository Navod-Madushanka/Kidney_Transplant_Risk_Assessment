# app/tests/integration/test_audit_logs.py
"""
Coverage for the audit_logs hash chain (see app/services/audit_service.py)
and the /audit-logs/verify endpoint, plus the compatibility-check flow's
shared-transaction fix (app/api/compatibility.py) that keeps a MatchReport
and its audit entry from ever getting split by a crash between them.
"""
import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.match_report import MatchReport
from app.services.abo_service import ABOResult
from app.services.audit_service import GENESIS_HASH, compute_audit_hash, create_audit_log
from app.services.match_pipeline import MatchPipelineResult
from app.services.match_report_service import create_match_report
from app.tests.conftest import create_donor, create_patient


async def _promote_to_admin(db_session: AsyncSession) -> None:
    """/audit-logs/verify and GET /audit-logs are admin-only (review #2 bug
    12) -- there's no self-service promotion path, so tests that need one
    reach into the DB directly, exactly like an operator would."""
    await db_session.execute(text("UPDATE doctors SET is_admin = true"))
    await db_session.commit()


async def test_running_a_check_writes_a_verifiable_audit_entry(
    auth_client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")  # ABO-incompatible -> halts fast

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    assert response.status_code == 201
    report_id = response.json()["id"]

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ran_compatibility_check")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].details["match_report_id"] == report_id
    assert len(entries[0].hash) == 64

    # audit_logs is truncated after every test (see conftest.py's
    # _clean_tables), so the very first row of the chain -- created_patient,
    # from the create_patient() call above -- is deterministically genesis.
    first_entry = (
        await db_session.execute(select(AuditLog).order_by(AuditLog.created_at.asc()).limit(1))
    ).scalar_one()
    assert first_entry.action == "created_patient"
    assert first_entry.prev_hash == GENESIS_HASH

    await _promote_to_admin(db_session)
    verify_response = await auth_client.get("/audit-logs/verify")
    assert verify_response.status_code == 200
    assert verify_response.json()["is_valid"] is True


async def test_verify_endpoint_requires_admin(auth_client: AsyncClient, db_session: AsyncSession):
    # Review #2 bug 12: this endpoint used to be reachable by any
    # authenticated doctor, despite exposing every doctor's activity
    # system-wide.
    response = await auth_client.get("/audit-logs/verify")
    assert response.status_code == 403

    # Authorization is re-checked live against the DB on every request
    # (get_current_user always re-fetches the doctor row), not read from
    # the JWT payload -- so promoting the same already-issued token's
    # doctor to admin, with no new login/token, takes effect immediately.
    await _promote_to_admin(db_session)

    response = await auth_client.get("/audit-logs/verify")
    assert response.status_code == 200


async def test_list_audit_logs_requires_admin(auth_client: AsyncClient, db_session: AsyncSession):
    response = await auth_client.get("/audit-logs")
    assert response.status_code == 403

    await _promote_to_admin(db_session)

    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    response = await auth_client.get("/audit-logs")
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] >= 3  # created_patient, created_donor, ran_compatibility_check
    assert body["rows"][0]["seq"] > body["rows"][-1]["seq"]  # newest first


async def test_verify_detects_a_rewritten_row_id(auth_client: AsyncClient, db_session: AsyncSession):
    # Review #2 bug 16: the row's own id wasn't part of the hash digest --
    # rewriting it (e.g. swapping which row is which) touched no hashed
    # field and used to pass verification.
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    row = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "ran_compatibility_check"))
    ).scalar_one()
    await db_session.execute(
        text("UPDATE audit_logs SET id = :new_id WHERE id = :old_id"),
        {"new_id": uuid.uuid4(), "old_id": row.id},
    )
    await db_session.commit()
    await _promote_to_admin(db_session)

    verify_response = await auth_client.get("/audit-logs/verify")
    assert verify_response.status_code == 200
    assert verify_response.json()["is_valid"] is False


async def test_verify_endpoint_detects_tampering(auth_client: AsyncClient, db_session: AsyncSession):
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    await db_session.execute(
        text("UPDATE audit_logs SET action = 'tampered_action' WHERE action = 'ran_compatibility_check'")
    )
    await db_session.commit()
    await _promote_to_admin(db_session)

    verify_response = await auth_client.get("/audit-logs/verify")

    assert verify_response.status_code == 200
    body = verify_response.json()
    assert body["is_valid"] is False
    assert body["reason"] is not None


async def test_verify_detects_a_deleted_middle_row_via_seq_gap(
    auth_client: AsyncClient, db_session: AsyncSession
):
    """Review #2 bug 1: deleting a row used to only be caught when it broke
    the prev_hash link to the *next* row -- the seq gap check catches a
    middle deletion independently of that, and is the mechanism this test
    is really targeting (see its reason string below)."""
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    middle_row = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "created_donor")
        )
    ).scalar_one()
    await db_session.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": middle_row.id})
    await db_session.commit()
    await _promote_to_admin(db_session)

    verify_response = await auth_client.get("/audit-logs/verify")
    assert verify_response.status_code == 200
    body = verify_response.json()
    assert body["is_valid"] is False
    assert "seq gap" in body["reason"]


async def test_verify_survives_a_clock_step_backwards(
    auth_client: AsyncClient, db_session: AsyncSession
):
    """Review #2 bug 2: verify_audit_chain used to order by created_at, so
    a clock correction that made a later write's created_at earlier than an
    prior write's would make the chain look permanently tampered. Ordering
    by seq instead means write order (not clock time) is what's actually
    verified.

    Builds the two rows directly (rather than editing created_at on an
    already-hashed row after the fact) since created_at is itself part of
    the hash payload -- retroactively editing it on a real row is
    indistinguishable from tampering and would correctly fail verification
    for an unrelated reason. This constructs what create_audit_log itself
    would have produced if the wall clock had genuinely stepped backwards
    between two real, back-to-back writes: each row's hash is computed
    from its own (out-of-order) created_at, exactly as it would be if
    create_audit_log had actually run at that moment.
    """
    doctor_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    first_id = uuid.uuid4()
    first_created_at = now
    first_hash = compute_audit_hash(
        GENESIS_HASH, doctor_id, None, None, "action_one", first_created_at, None, first_id
    )
    db_session.add(
        AuditLog(
            id=first_id,
            doctor_id=doctor_id,
            action="action_one",
            created_at=first_created_at,
            prev_hash=GENESIS_HASH,
            hash=first_hash,
        )
    )
    await db_session.commit()

    second_id = uuid.uuid4()
    second_created_at = now - timedelta(hours=1)  # NTP stepped the clock back
    second_hash = compute_audit_hash(
        first_hash, doctor_id, None, None, "action_two", second_created_at, None, second_id
    )
    db_session.add(
        AuditLog(
            id=second_id,
            doctor_id=doctor_id,
            action="action_two",
            created_at=second_created_at,
            prev_hash=first_hash,
            hash=second_hash,
        )
    )
    await db_session.commit()
    await _promote_to_admin(db_session)

    verify_response = await auth_client.get("/audit-logs/verify")
    assert verify_response.status_code == 200
    assert verify_response.json()["is_valid"] is True


async def test_verify_does_not_yet_catch_a_deleted_tail_row(
    auth_client: AsyncClient, db_session: AsyncSession
):
    """Documents the known, still-open limitation from review #2 bug 1:
    deleting the newest row leaves a chain (and seq run) that's still
    internally consistent -- closing this needs a write-side protection
    (e.g. revoking DELETE from the app's DB role), not a read-time check.
    This test exists so that gap gets closed on purpose, not accidentally
    papered over by a future change to verify_audit_chain."""
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    await db_session.execute(
        text("DELETE FROM audit_logs WHERE seq = (SELECT MAX(seq) FROM audit_logs)")
    )
    await db_session.commit()
    await _promote_to_admin(db_session)

    verify_response = await auth_client.get("/audit-logs/verify")
    assert verify_response.status_code == 200
    assert verify_response.json()["is_valid"] is True


async def test_match_report_and_audit_entry_share_one_transaction(
    auth_client: AsyncClient, db_session: AsyncSession
):
    """Regression test for the finding that create_audit_log used to commit
    independently of create_match_report, so a failure between the two
    could leave a report on record with no audit trail for it. Both now
    take commit=False and the caller (app/api/compatibility.py) issues one
    db.commit() for both -- this reproduces that pattern directly against
    the service layer and proves a rollback discards both together, not
    just one of them.
    """
    # match_reports.patient_id/donor_id are real foreign keys -- need actual
    # rows, not arbitrary UUIDs, or the flush below fails for an unrelated
    # reason (FK violation) before the thing under test ever runs.
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    patient_id = uuid.UUID(patient["id"])
    donor_id = uuid.UUID(donor["id"])
    pipeline_result = MatchPipelineResult(
        overall_status="halted_abo_fail",
        abo_result=ABOResult(is_compatible=False, recipient_type="O", donor_type="A"),
    )

    report = await create_match_report(db_session, patient_id, donor_id, pipeline_result, commit=False)
    await create_audit_log(
        db_session,
        doctor_id=uuid.uuid4(),
        action="ran_compatibility_check",
        patient_id=patient_id,
        donor_id=donor_id,
        details={"match_report_id": str(report.id)},
        commit=False,
    )

    await db_session.rollback()

    report_result = await db_session.execute(select(MatchReport).where(MatchReport.id == report.id))
    # Filtered by action, not just patient_id -- create_patient's own
    # "created_patient" audit entry is a real, already-committed row for
    # this same patient_id (from the setup call above), so a bare
    # patient_id filter would match it too and defeat the point of this
    # test, which is specifically about the ran_compatibility_check entry
    # that was just rolled back.
    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.patient_id == patient_id, AuditLog.action == "ran_compatibility_check"
        )
    )
    assert report_result.scalar_one_or_none() is None
    assert audit_result.scalar_one_or_none() is None

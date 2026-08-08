# app/tests/integration/test_audit_logs.py
"""
Coverage for the audit_logs hash chain (see app/services/audit_service.py)
and the /audit-logs/verify endpoint, plus the compatibility-check flow's
shared-transaction fix (app/api/compatibility.py) that keeps a MatchReport
and its audit entry from ever getting split by a crash between them.
"""
import uuid

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.match_report import MatchReport
from app.services.abo_service import ABOResult
from app.services.audit_service import GENESIS_HASH, create_audit_log
from app.services.match_pipeline import MatchPipelineResult
from app.services.match_report_service import create_match_report
from app.tests.conftest import create_donor, create_patient


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
    # audit_logs is truncated after every test (see conftest.py's
    # _clean_tables) and neither create_patient nor create_donor audit-logs
    # anything, so this is deterministically the first row in the chain.
    assert entries[0].prev_hash == GENESIS_HASH
    assert len(entries[0].hash) == 64

    verify_response = await auth_client.get("/audit-logs/verify")
    assert verify_response.status_code == 200
    assert verify_response.json()["is_valid"] is True


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

    verify_response = await auth_client.get("/audit-logs/verify")

    assert verify_response.status_code == 200
    body = verify_response.json()
    assert body["is_valid"] is False
    assert body["reason"] is not None


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
    audit_result = await db_session.execute(
        select(AuditLog).where(AuditLog.patient_id == patient_id)
    )
    assert report_result.scalar_one_or_none() is None
    assert audit_result.scalar_one_or_none() is None

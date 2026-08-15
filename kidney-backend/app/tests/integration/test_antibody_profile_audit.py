# app/tests/integration/test_antibody_profile_audit.py
"""
Coverage for Part J's (J4/J5) antibody-profile overwrite audit trail.
replace_patient_antibody_profiles is a hard delete-then-insert with no
history table -- every overwrite destroys the prior profile outright, with
no undo short of a human re-transcribing the source chart. The audit log's
`details` JSONB is the cheapest sufficient fix that ships without a new
table: capture what's about to be deleted before deleting it, and tag who/
what wrote it. See app/services/antibody_profile_service.py's docstring.
"""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.tests.conftest import create_patient


async def _last_replace_entry(db_session: AsyncSession) -> AuditLog:
    result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.action == "replaced_patient_antibody_profiles")
        .order_by(AuditLog.seq.desc())
        .limit(1)
    )
    return result.scalar_one()


async def test_overwriting_a_profile_records_the_replaced_rows_in_the_audit_log(
    auth_client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client)
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "A2", "mfi": 3500}, {"antigen": "B7", "mfi": 1200}],
    )

    # The overwrite that actually needs to be recoverable -- these two rows
    # are about to be hard-deleted.
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "DQ7", "mfi": 900}],
    )

    entry = await _last_replace_entry(db_session)
    replaced = {(e["antigen"], e["mfi"]) for e in entry.details["replaced_entries"]}
    # Enough to reconstruct the prior profile by hand: antigen + the exact
    # MFI string as stored (NUMERIC(10,2), so always two decimal places).
    assert replaced == {("A2", "3500.00"), ("B7", "1200.00")}


async def test_first_write_to_an_empty_profile_records_no_replaced_entries(
    auth_client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client)
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "A2", "mfi": 3500}],
    )

    entry = await _last_replace_entry(db_session)
    assert entry.details["replaced_entries"] == []


async def test_manual_put_is_tagged_with_source_manual_and_no_job_id(
    auth_client: AsyncClient, db_session: AsyncSession
):
    # After Part J deleted the OCR job's unattended auto-save (see
    # test_ocr_jobs.py's test_bead_specificity_job_with_patient_id_writes_
    # nothing_to_antibody_profiles), this PUT endpoint is the ONLY
    # production caller left -- source should reflect that rather than
    # being indistinguishable from a hypothetical future automated write.
    patient = await create_patient(auth_client)
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "A2", "mfi": 3500}],
    )

    entry = await _last_replace_entry(db_session)
    assert entry.details["source"] == "manual"
    assert entry.details["job_id"] is None


async def test_replacing_without_ocr_verified_preserves_prior_flag(auth_client: AsyncClient):
    # The Part E "no claim" contract (review #2 bug 5) -- see
    # test_compatibility.py's test_replacing_hla_typing_without_ocr_
    # verified_preserves_prior_unverified_state for the HLA-typing
    # equivalent of this same fix. Omitting ocr_verified must not silently
    # reset an existing unverified profile back to trusted.
    patient = await create_patient(auth_client)
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "A2", "mfi": 3500}],
        params={"ocr_verified": "false"},
    )

    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "A2", "mfi": 3500}],
    )

    patient_response = await auth_client.get(f"/patients/{patient['id']}")
    assert patient_response.json()["antibody_profile_verified"] is False

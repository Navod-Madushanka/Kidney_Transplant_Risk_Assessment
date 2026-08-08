# app/tests/integration/test_donor_search_service.py
"""
Service-level coverage for app/services/donor_search_service.py, talking to
the DB directly (needed for the Donor/Doctor/Hospital join) rather than
through HTTP — the HTTP-level ownership/PII/audit behavior is covered
separately in test_donor_search.py.
"""
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.services.donor_search_service import search_compatible_donors
from app.tests.conftest import create_donor, create_patient


async def _load_patient(db_session: AsyncSession, patient_id: str) -> Patient:
    result = await db_session.execute(select(Patient).where(Patient.id == uuid.UUID(patient_id)))
    return result.scalar_one()


async def test_excludes_non_available_donors(
    auth_client: AsyncClient, second_auth_client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(second_auth_client, blood_type="O")
    await second_auth_client.put(f"/donors/{donor['id']}/status", json={"status": "reserved"})

    patient_obj = await _load_patient(db_session, patient["id"])
    requesting_doctor_id = uuid.UUID(patient["doctor_id"])
    candidates = await search_compatible_donors(db_session, patient_obj, requesting_doctor_id)

    assert candidates == []


async def test_excludes_requesting_doctors_own_donors(
    auth_client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client, blood_type="AB")
    await create_donor(auth_client, blood_type="O")

    patient_obj = await _load_patient(db_session, patient["id"])
    requesting_doctor_id = uuid.UUID(patient["doctor_id"])
    candidates = await search_compatible_donors(db_session, patient_obj, requesting_doctor_id)

    assert candidates == []


async def test_excludes_abo_incompatible_donors(
    auth_client: AsyncClient, second_auth_client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client, blood_type="O")
    await create_donor(second_auth_client, blood_type="A")

    patient_obj = await _load_patient(db_session, patient["id"])
    requesting_doctor_id = uuid.UUID(patient["doctor_id"])
    candidates = await search_compatible_donors(db_session, patient_obj, requesting_doctor_id)

    assert candidates == []


async def test_ranks_by_ascending_mismatch_count(
    auth_client: AsyncClient, second_auth_client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client, blood_type="AB")
    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )

    perfect_match = await create_donor(
        second_auth_client, blood_type="O", full_name="Perfect Match"
    )
    await second_auth_client.put(
        f"/donors/{perfect_match['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )

    # 2 unique mismatches per locus x 3 loci = 6 total — the maximum
    # reachable count that still doesn't halt (MAX_ACCEPTABLE_MISMATCHES == 6).
    mismatched = await create_donor(second_auth_client, blood_type="O", full_name="Mismatched")
    await second_auth_client.put(
        f"/donors/{mismatched['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "11", "allele_2": "12"},
            {"locus": "B", "allele_1": "17", "allele_2": "18"},
            {"locus": "DRB1", "allele_1": "13", "allele_2": "14"},
        ],
    )

    patient_obj = await _load_patient(db_session, patient["id"])
    requesting_doctor_id = uuid.UUID(patient["doctor_id"])
    candidates = await search_compatible_donors(db_session, patient_obj, requesting_doctor_id)

    assert [c.donor.id for c in candidates] == [
        uuid.UUID(perfect_match["id"]),
        uuid.UUID(mismatched["id"]),
    ]
    assert candidates[0].mismatch_result.total_mismatches == 0
    assert candidates[1].mismatch_result.total_mismatches == 6


async def test_missing_donor_and_patient_hla_typing_does_not_crash(
    auth_client: AsyncClient, second_auth_client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client, blood_type="AB")
    await create_donor(second_auth_client, blood_type="O")

    patient_obj = await _load_patient(db_session, patient["id"])
    requesting_doctor_id = uuid.UUID(patient["doctor_id"])
    candidates = await search_compatible_donors(db_session, patient_obj, requesting_doctor_id)

    # Regression coverage: an untyped donor/patient pair must NOT resolve to
    # a perfect (0-mismatch) match -- each of the 3 counted loci is missing
    # on both sides, so each is scored at its worst case (2 x 3 = 6), and the
    # result is flagged incomplete so callers never present this as a real
    # compatibility figure. See hla_mismatch_service.py.
    assert len(candidates) == 1
    assert candidates[0].mismatch_result.total_mismatches == 6
    assert candidates[0].mismatch_result.data_completeness is False


async def test_empty_pool_returns_empty_list(auth_client: AsyncClient, db_session: AsyncSession):
    patient = await create_patient(auth_client, blood_type="AB")

    patient_obj = await _load_patient(db_session, patient["id"])
    requesting_doctor_id = uuid.UUID(patient["doctor_id"])
    candidates = await search_compatible_donors(db_session, patient_obj, requesting_doctor_id)

    assert candidates == []

# app/tests/integration/test_donor_search.py
"""
HTTP-level coverage for GET /patients/{id}/compatible-donors — the
cross-hospital donor search endpoint. The prescreen math itself (ABO +
mismatch filtering/ranking) is covered directly against the service in
test_donor_search_service.py; these tests check ownership enforcement, the
PII boundary, and the audit trail.
"""
import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.tests.conftest import create_donor, create_patient

DONOR_PII_FIELDS = {"full_name", "date_of_birth", "nic_number", "doctor_id"}


async def test_search_requires_own_patient(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    other_patient = await create_patient(second_auth_client)

    response = await auth_client.get(f"/patients/{other_patient['id']}/compatible-donors")

    assert response.status_code == 404


async def test_search_excludes_own_available_donors(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")
    await create_donor(auth_client, blood_type="O")

    response = await auth_client.get(f"/patients/{patient['id']}/compatible-donors")

    assert response.status_code == 200
    assert response.json() == []


async def test_search_excludes_reserved_and_transplanted_donors(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    patient = await create_patient(auth_client, blood_type="AB")
    reserved_donor = await create_donor(second_auth_client, blood_type="O")
    transplanted_donor = await create_donor(second_auth_client, blood_type="O")

    await second_auth_client.put(
        f"/donors/{reserved_donor['id']}/status", json={"status": "reserved"}
    )
    await second_auth_client.put(
        f"/donors/{transplanted_donor['id']}/status", json={"status": "transplanted"}
    )

    response = await auth_client.get(f"/patients/{patient['id']}/compatible-donors")

    assert response.status_code == 200
    assert response.json() == []


async def test_search_excludes_abo_incompatible_donors(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    # Recipient O only accepts an O donor (app/reference_data/abo_compatibility.py).
    patient = await create_patient(auth_client, blood_type="O")
    await create_donor(second_auth_client, blood_type="A")

    response = await auth_client.get(f"/patients/{patient['id']}/compatible-donors")

    assert response.status_code == 200
    assert response.json() == []


async def test_search_returns_other_doctors_donor_with_hospital_and_doctor_name_but_no_pii(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    # Matching A/B/DRB1 typing on both sides so Step 3's mismatch gate
    # doesn't exclude this candidate — an entirely untyped pairing now
    # worst-cases to a reject (see test_missing_donor_and_patient_hla_typing_
    # does_not_crash in test_donor_search_service.py), which isn't what this
    # PII/shape test is about.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(second_auth_client, blood_type="O", full_name="Secret Donor Name")
    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )
    await second_auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )

    response = await auth_client.get(f"/patients/{patient['id']}/compatible-donors")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    candidate = body[0]

    assert candidate["donor_id"] == donor["id"]
    assert candidate["hospital_name"] == "Second Test Hospital"
    assert candidate["doctor_full_name"] == "Dr. Second Doctor"
    assert "@" in candidate["doctor_email"]
    assert candidate["blood_type"] == "O"
    assert candidate["status"] == "available"
    assert candidate["abo_result"]["is_compatible"] is True

    assert DONOR_PII_FIELDS.isdisjoint(candidate.keys())
    assert "Secret Donor Name" not in str(candidate)


async def test_search_empty_pool_returns_empty_list_not_404(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")

    response = await auth_client.get(f"/patients/{patient['id']}/compatible-donors")

    assert response.status_code == 200
    assert response.json() == []


async def test_search_writes_audit_log_entry(
    auth_client: AsyncClient, second_auth_client: AsyncClient, db_session
):
    # Matching A/B/DRB1 typing on both sides so Step 3's mismatch gate
    # doesn't exclude this candidate — see the sibling PII test above for
    # why an untyped pairing no longer works for this.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(second_auth_client, blood_type="O")
    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )
    await second_auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )

    response = await auth_client.get(f"/patients/{patient['id']}/compatible-donors")
    assert response.status_code == 200

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "searched_cross_hospital_donors")
    )
    entries = result.scalars().all()

    assert len(entries) == 1
    assert entries[0].patient_id == uuid.UUID(patient["id"])
    assert entries[0].details["result_count"] == 1

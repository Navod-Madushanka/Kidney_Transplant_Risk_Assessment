# app/tests/integration/test_compatibility.py
"""
Integration coverage for the compatibility-check pipeline through the real
HTTP API. The pipeline's individual stages (ABO, DSA, HLA scoring, cPRA,
sensitization, risk tiering) already have thorough unit coverage in
app/tests/unit/ — these tests instead check that the API wires patient/donor
records through the whole pipeline correctly and persists/returns the right
thing, using the two halt paths (ABO fail, DSA trigger) and one full run
that reaches HLA scoring.
"""
from httpx import AsyncClient

from app.tests.conftest import (
    COMPATIBLE_DONOR_HLA,
    COMPATIBLE_PATIENT_HLA,
    create_donor,
    create_patient,
)


async def test_check_compatibility_requires_existing_patient_and_donor(auth_client: AsyncClient):
    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": "00000000-0000-0000-0000-000000000000",
            "donor_id": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 404


async def test_abo_incompatible_pair_halts_before_hla_scoring(auth_client: AsyncClient):
    # Recipient O only accepts an O donor (app/reference_data/abo_compatibility.py)
    # — pairing with an A donor should halt immediately.
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_abo_fail"
    assert body["abo_result"]["is_compatible"] is False
    assert body["sensitization_result"] is None
    assert body["hla_scoring_result"] is None


async def test_dsa_match_halts_before_hla_scoring(auth_client: AsyncClient):
    # ABO-compatible pair (O -> O), but the patient carries a high-MFI
    # antibody against an antigen the donor actually has — should halt on
    # the DSA check before HLA scoring ever runs (app/services/dsa_service.py).
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "B7", "mfi": 3500}],
    )
    await auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[{"locus": "B", "allele_1": "07", "allele_2": "40"}],
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_dsa_trigger"
    assert body["dsa_result"]["is_halted"] is True
    assert body["hla_scoring_result"] is None


async def test_full_pipeline_run_reaches_hla_scoring_and_risk_tier(auth_client: AsyncClient):
    # AB recipient accepts any donor blood type, and with no antibody
    # profile on file the DSA check can't trigger, so this pair should run
    # the full pipeline through to HLA scoring and cPRA.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "completed"
    assert body["abo_result"]["is_compatible"] is True
    # Ground truth from the project's worked lab example
    # (app/tests/unit/test_hla_scoring_service.py): this exact typing pair
    # scores 6.5, which lands in "High-Moderate Risk" (5.25-7.0).
    assert body["hla_scoring_result"]["total_score"] == 6.5
    assert body["cpra_result"] is not None


async def test_get_report_by_id(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    check = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    report_id = check.json()["id"]

    response = await auth_client.get(f"/compatibility/reports/{report_id}")

    assert response.status_code == 200
    assert response.json()["id"] == report_id


async def test_get_nonexistent_report_is_404(auth_client: AsyncClient):
    response = await auth_client.get(
        "/compatibility/reports/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


async def test_cannot_get_another_doctors_report(auth_client: AsyncClient, client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    check = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    report_id = check.json()["id"]

    other_doctor_payload = {
        "hospital_name": "Other Hospital",
        "email": "third-doctor@example.com",
        "password": "another-secret-1234",
        "full_name": "Dr. Third",
    }
    await client.post("/auth/register", json=other_doctor_payload)
    login = await client.post(
        "/auth/login",
        json={"email": other_doctor_payload["email"], "password": other_doctor_payload["password"]},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get(f"/compatibility/reports/{report_id}", headers=other_headers)

    assert response.status_code == 404

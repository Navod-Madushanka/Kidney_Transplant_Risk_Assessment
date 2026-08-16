# app/tests/integration/test_compatibility_readiness.py
"""
GET /compatibility/readiness -- see app/services/compatibility_precondition_
service.py's module docstring for the blocking-vs-score-gap distinction
this preview exists to surface before a doctor ever submits the wizard.
"""
from httpx import AsyncClient

from app.tests.conftest import (
    COMPATIBLE_DONOR_HLA,
    COMPATIBLE_PATIENT_HLA,
    create_donor,
    create_patient,
)


def _gap_codes(gaps):
    return {gap["code"] for gap in gaps}


async def test_complete_pair_is_ready_with_no_gaps(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB", sex="female", weight_kg=60)
    donor = await create_donor(
        auth_client,
        blood_type="O",
        sex="male",
        race="white",
        smoking_status="never",
        egfr=95,
        bmi=24.5,
        systolic_bp=118,
        diastolic_bp=76,
        has_diabetes=False,
        urine_acr=10,
        is_on_antihypertensive_medication=False,
        weight_kg=78,
        is_biologically_related=True,
    )
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.get(
        f"/compatibility/readiness?patient_id={patient['id']}&donor_id={donor['id']}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_run"] is True
    assert body["blocking"] == []
    assert body["lkdpi_gaps"] == []
    assert body["donor_risk_projection_gaps"] == []
    assert body["donor_risk_contraindication_gaps"] == []


async def test_donor_missing_weight_is_a_score_gap_not_blocking(auth_client: AsyncClient):
    # D3/E2.3's deliberate asymmetry: a missing LKDPI input never blocks the
    # check itself -- only the score is withheld.
    patient = await create_patient(auth_client, blood_type="AB", sex="female", weight_kg=60)
    donor = await create_donor(auth_client, blood_type="O")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.get(
        f"/compatibility/readiness?patient_id={patient['id']}&donor_id={donor['id']}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_run"] is True
    assert body["blocking"] == []
    assert "lkdpi_donor_weight" in _gap_codes(body["lkdpi_gaps"])
    assert any(gap["subject"] == "donor" for gap in body["lkdpi_gaps"])


async def test_missing_hla_typing_is_blocking(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")
    # Neither side has any HLA typing entered at all.

    response = await auth_client.get(
        f"/compatibility/readiness?patient_id={patient['id']}&donor_id={donor['id']}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_run"] is False
    assert len(body["blocking"]) > 0


async def test_unverified_patient_details_is_blocking(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB", details_verified=False)
    donor = await create_donor(auth_client, blood_type="O")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.get(
        f"/compatibility/readiness?patient_id={patient['id']}&donor_id={donor['id']}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_run"] is False
    assert "patient_details_unverified" in _gap_codes(body["blocking"])


async def test_unverified_antibody_profile_is_not_blocking(auth_client: AsyncClient):
    # BeadSpecificityStep.jsx has its own dedicated wizard step that
    # re-confirms this exact data (reading patientRecord.
    # antibody_profile_verified the same way this flag does), regardless
    # of whether this session is what extracted it -- blocking Continue
    # here would only dead-end the doctor into a detour to the patient's
    # profile page for something the wizard already asks them to review a
    # few steps later. POST /compatibility/check's own hard block (see
    # test_compatibility.py's test_unverified_antibody_profile_blocks_
    # the_check) is unaffected by this -- it still refuses to run.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "B7", "mfi": 500}],
        params={"ocr_verified": "false"},
    )

    response = await auth_client.get(
        f"/compatibility/readiness?patient_id={patient['id']}&donor_id={donor['id']}"
    )

    assert response.status_code == 200
    body = response.json()
    assert "patient_antibody_profile_unverified" not in _gap_codes(body["blocking"])
    assert body["can_run"] is True


async def test_readiness_404s_for_nonexistent_patient_same_as_check(auth_client: AsyncClient):
    donor = await create_donor(auth_client, blood_type="O")

    response = await auth_client.get(
        "/compatibility/readiness"
        f"?patient_id=00000000-0000-0000-0000-000000000000&donor_id={donor['id']}"
    )

    assert response.status_code == 404


async def test_readiness_404s_for_nonexistent_donor_same_as_check(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")

    response = await auth_client.get(
        "/compatibility/readiness"
        f"?patient_id={patient['id']}&donor_id=00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


async def test_donor_missing_clinical_fields_is_a_donor_risk_gap(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB", sex="female", weight_kg=60)
    donor = await create_donor(auth_client, blood_type="O", weight_kg=78)
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.get(
        f"/compatibility/readiness?patient_id={patient['id']}&donor_id={donor['id']}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_run"] is True
    assert len(body["donor_risk_projection_gaps"]) > 0
    assert all(gap["subject"] == "donor" for gap in body["donor_risk_projection_gaps"])

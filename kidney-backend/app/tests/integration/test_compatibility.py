# app/tests/integration/test_compatibility.py
"""
Integration coverage for the compatibility-check pipeline through the real
HTTP API. The pipeline's individual stages (ABO, mismatch bucketing, PRA
bucketing, DSA, crossmatch, risk classification, sensitization, legacy risk
tiering) already have thorough unit coverage in app/tests/unit/ — these
tests instead check that the API wires patient/donor records through the
whole Step 1-7 sequence correctly and persists/returns the right thing.

Two of the seven steps' reject paths are deliberately NOT covered here:
- Step 3 (mismatches): with exactly two alleles per locus across the three
  counted loci (A/B/DRB1), the maximum possible mismatch count is 6 — the
  same number as MAX_ACCEPTABLE_MISMATCHES. The ">6 mismatches" reject
  bucket can't actually be reached through normal typing data, so there's
  nothing realistic to construct here; see
  test_hla_mismatch_service.py::test_maximum_reachable_mismatches_lands_in_top_bucket_without_halting.
- Step 4 (PRA): halting requires cPRA to have "sufficient data", which
  needs >= 100 people's HLA typing already in the population sample
  (app/reference_data/cpra_settings.py). Seeding that many patient/donor
  pairs just for this test isn't worth the runtime cost — the bucket
  math itself is covered precisely and quickly in test_pra_bucket_service.py.
"""
from httpx import AsyncClient

from app.tests.conftest import (
    COMPATIBLE_DONOR_HLA,
    COMPATIBLE_PATIENT_HLA,
    create_donor,
    create_patient,
)

NEGATIVE_CROSSMATCH = {
    "is_positive": False,
    "t_cell_result": "Negative",
    "b_cell_result": "Negative",
}

POSITIVE_CROSSMATCH = {
    "is_positive": True,
    "t_cell_result": "Positive",
    "b_cell_result": "Negative",
}


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
    # the full pipeline through to HLA scoring and cPRA — as long as a
    # crossmatch result is also submitted, since Step 6 now requires one to
    # reach "completed" rather than stopping at "pending_crossmatch".
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient["id"],
            "donor_id": donor["id"],
            "crossmatch": NEGATIVE_CROSSMATCH,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "completed"
    assert body["abo_result"]["is_compatible"] is True
    # Ground truth from the project's worked lab example
    # (app/tests/unit/test_hla_scoring_service.py): this exact typing pair
    # scores 6.5 on the legacy all-9-loci score, which lands in
    # "High-Moderate Risk" (5.25-7.0) — kept for reference alongside the
    # new Step 3/4/7 results below.
    assert body["hla_scoring_result"]["total_score"] == 6.5
    assert body["cpra_result"] is not None

    # New Step 3 (mismatches, A/B/DRB1 only): this typing pair has 3 total
    # mismatches across those three loci (2 at DRB1, 1 at B, 0 at A) -> the
    # "3-6 mismatches" bucket, which doesn't halt.
    assert body["mismatch_result"]["total_mismatches"] == 3
    assert body["mismatch_result"]["bucket_name"] == "3-6 mismatches"
    assert body["mismatch_result"]["is_halted"] is False

    # New Step 6 (crossmatch): negative, so it's recorded but doesn't halt.
    assert body["crossmatch_result"]["is_positive"] is False
    assert body["crossmatch_result"]["is_halted"] is False

    # New Step 7 (final risk classification): a lone patient/donor pair in
    # a freshly-truncated test DB is nowhere near cPRA's 100-person minimum
    # sample size, so Step 4's PRA bucket is None and Step 7 correctly
    # declines to guess a final risk level rather than assuming "low".
    assert body["pra_bucket_result"]["has_sufficient_data"] is False
    assert body["pra_bucket_result"]["bucket_name"] is None
    assert body["final_risk_level"] is None


async def test_positive_crossmatch_halts_after_dsa(auth_client: AsyncClient):
    # Same compatible pair as the full-pipeline test above (passes Steps
    # 1/3/4/5), but this time with a positive crossmatch — should halt at
    # the new Step 6 instead of reaching a final classification.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient["id"],
            "donor_id": donor["id"],
            "crossmatch": POSITIVE_CROSSMATCH,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_crossmatch_positive"
    assert body["crossmatch_result"]["is_positive"] is True
    assert body["crossmatch_result"]["is_halted"] is True
    # Everything through Step 5 still ran and is on the report.
    assert body["dsa_result"] is not None
    assert body["mismatch_result"] is not None
    # But Step 7 never ran.
    assert body["final_risk_level"] is None
    assert body["hla_scoring_result"] is None


async def test_check_without_crossmatch_stops_at_pending(auth_client: AsyncClient):
    # Same compatible pair, but no crossmatch submitted at all — every gate
    # through Step 5 passes, but the check can't be treated as "completed"
    # without a crossmatch result.
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
    assert body["overall_status"] == "pending_crossmatch"
    assert body["crossmatch_result"] is None
    assert body["dsa_result"] is not None
    assert body["final_risk_level"] is None


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

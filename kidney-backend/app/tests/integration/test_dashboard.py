# app/tests/integration/test_dashboard.py
from httpx import AsyncClient

from app.tests.conftest import (
    COMPATIBLE_DONOR_HLA,
    COMPATIBLE_PATIENT_HLA,
    create_donor,
    create_patient,
)


async def test_dashboard_patients_empty_for_new_doctor(auth_client: AsyncClient):
    response = await auth_client.get("/dashboard/patients")

    assert response.status_code == 200
    assert response.json() == []


async def test_dashboard_patients_lists_patient_with_no_report_yet(auth_client: AsyncClient):
    await create_patient(auth_client)

    response = await auth_client.get("/dashboard/patients")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["latest_report"] is None


async def test_dashboard_patients_shows_latest_report_summary(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)
    await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient["id"],
            "donor_id": donor["id"],
            # Step 6 (crossmatch) now gates "completed" — without one the
            # pipeline stops at "pending_crossmatch" (see
            # test_compatibility.py::test_check_without_crossmatch_stops_at_pending).
            # This test is about the dashboard summary shape, not the
            # crossmatch gate itself, so submit a negative result to reach
            # "completed" like it always used to.
            "crossmatch": {
                "is_positive": False,
                "t_cell_result": "Negative",
                "b_cell_result": "Negative",
            },
        },
    )

    response = await auth_client.get("/dashboard/patients")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["latest_report"]["overall_status"] == "completed"
    # Same worked-example typing pair used in test_compatibility.py: total
    # score 6.5 -> "High-Moderate Risk" (app/reference_data/risk_tiers.py).
    # This is the legacy continuous-score tier, kept for reference.
    assert body[0]["latest_report"]["risk_tier"] == "High-Moderate Risk"
    # The new Step 7 classification, by contrast, is None here: a lone
    # patient/donor pair in a freshly-truncated test DB is nowhere near
    # cPRA's 100-person minimum sample size, so there's no PRA bucket to
    # combine with the mismatch bucket (see
    # test_compatibility.py::test_full_pipeline_run_reaches_hla_scoring_and_risk_tier).
    assert body[0]["latest_report"]["final_risk_level"] is None


async def test_dashboard_recent_reports_empty_for_new_doctor(auth_client: AsyncClient):
    response = await auth_client.get("/dashboard/reports/recent")

    assert response.status_code == 200
    assert response.json() == []


async def test_dashboard_recent_reports_includes_patient_and_donor_names(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="O", full_name="Recent Patient")
    donor = await create_donor(auth_client, blood_type="A", full_name="Recent Donor")
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    response = await auth_client.get("/dashboard/reports/recent")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["patient_full_name"] == "Recent Patient"
    assert body[0]["donor_full_name"] == "Recent Donor"
    # O -> A is ABO-incompatible, so this run should have halted.
    assert body[0]["overall_status"] == "halted_abo_fail"


async def test_dashboard_recent_reports_respects_limit(auth_client: AsyncClient):
    for _ in range(3):
        patient = await create_patient(auth_client, blood_type="O")
        donor = await create_donor(auth_client, blood_type="A")
        await auth_client.post(
            "/compatibility/check",
            json={"patient_id": patient["id"], "donor_id": donor["id"]},
        )

    response = await auth_client.get("/dashboard/reports/recent?limit=2")

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_dashboard_requires_auth(client: AsyncClient):
    response = await client.get("/dashboard/patients")

    assert response.status_code in (401, 403)

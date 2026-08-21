# app/tests/integration/test_dashboard.py
from httpx import AsyncClient

from app.tests.conftest import (
    COMPATIBLE_DONOR_HLA,
    COMPATIBLE_PATIENT_HLA,
    create_donor,
    create_patient,
    type_patient_and_donor_hla,
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
    # The new Step 7 classification: no antibody profile was submitted, so
    # cPRA is 0.0% against the frozen reference table -> PRA bucket "<30%"
    # (0 pts), combined with the "3-6 mismatches" mismatch bucket (2 pts) ->
    # "High-Average Risk" (see
    # test_compatibility.py::test_full_pipeline_run_reaches_hla_scoring_and_risk_tier,
    # same worked-example typing pair).
    assert body[0]["latest_report"]["final_risk_level"] == "High-Average Risk"


async def test_dashboard_patients_excludes_deleted_patient(auth_client: AsyncClient):
    patient = await create_patient(auth_client)

    delete_response = await auth_client.delete(f"/patients/{patient['id']}")
    assert delete_response.status_code == 204

    response = await auth_client.get("/dashboard/patients")

    assert response.status_code == 200
    assert response.json() == []


async def test_dashboard_recent_reports_empty_for_new_doctor(auth_client: AsyncClient):
    response = await auth_client.get("/dashboard/reports/recent")

    assert response.status_code == 200
    assert response.json() == []


async def test_dashboard_recent_reports_includes_patient_and_donor_names(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="O", full_name="Recent Patient")
    donor = await create_donor(auth_client, blood_type="A", full_name="Recent Donor")
    await type_patient_and_donor_hla(auth_client, patient["id"], donor["id"])
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
        await type_patient_and_donor_hla(auth_client, patient["id"], donor["id"])
        await auth_client.post(
            "/compatibility/check",
            json={"patient_id": patient["id"], "donor_id": donor["id"]},
        )

    response = await auth_client.get("/dashboard/reports/recent?limit=2")

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_dashboard_recent_reports_excludes_deleted_patient(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await type_patient_and_donor_hla(auth_client, patient["id"], donor["id"])
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    delete_response = await auth_client.delete(f"/patients/{patient['id']}")
    assert delete_response.status_code == 204

    response = await auth_client.get("/dashboard/reports/recent")

    assert response.status_code == 200
    assert response.json() == []


async def test_dashboard_recent_reports_excludes_deleted_donor(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await type_patient_and_donor_hla(auth_client, patient["id"], donor["id"])
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    delete_response = await auth_client.delete(f"/donors/{donor['id']}")
    assert delete_response.status_code == 204

    response = await auth_client.get("/dashboard/reports/recent")

    assert response.status_code == 200
    assert response.json() == []


async def test_dashboard_requires_auth(client: AsyncClient):
    response = await client.get("/dashboard/patients")

    assert response.status_code in (401, 403)


async def test_dashboard_recent_reports_masks_external_donor_name(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    # A cross-hospital check (see test_compatibility.py) puts a report on
    # the requesting doctor's dashboard referencing a donor they don't own —
    # that donor's real name must never leak onto this doctor's own view.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(second_auth_client, blood_type="O", full_name="Secret Donor Name")
    await type_patient_and_donor_hla(
        auth_client, patient["id"], donor["id"], donor_client=second_auth_client
    )
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    response = await auth_client.get("/dashboard/reports/recent")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["donor_full_name"] == "External donor"
    assert "Secret Donor Name" not in str(body)

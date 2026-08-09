# app/tests/integration/test_donor_risk_assessment.py
from datetime import date

from httpx import AsyncClient

from app.tests.conftest import create_donor

# 38 years old as of "today", whenever the suite actually runs -- safely
# mid-band for the model's 35-44 age band (see
# app/reference_data/donor_risk_model.py's AGE_BANDS) regardless of which
# real-world year the tests execute in.
_BIRTH_DATE = date.today().replace(year=date.today().year - 38).isoformat()

FULL_RISK_PAYLOAD = dict(
    date_of_birth=_BIRTH_DATE,
    egfr=98.0,
    systolic_bp=120,
    diastolic_bp=80,
    bmi=26.0,
    has_diabetes=False,
    smoking_status="never",
    sex="male",
    race="black",
    urine_acr=4.0,
    is_on_antihypertensive_medication=False,
    family_history_kidney_disease=False,
)


async def test_risk_assessment_requires_auth(auth_client: AsyncClient):
    # auth_client wraps the same underlying httpx client as the plain
    # `client` fixture (auth_client just sets the header on it), so drop
    # the header rather than taking `client` as a separate param -- see
    # test_delete_donor_requires_auth in test_donors.py for the same
    # pattern.
    donor = await create_donor(auth_client, **FULL_RISK_PAYLOAD)
    del auth_client.headers["Authorization"]

    response = await auth_client.get(f"/donors/{donor['id']}/risk-assessment")

    assert response.status_code in (401, 403)


async def test_risk_assessment_404s_for_nonexistent_donor(auth_client: AsyncClient):
    response = await auth_client.get(
        "/donors/00000000-0000-0000-0000-000000000000/risk-assessment"
    )

    assert response.status_code == 404


async def test_risk_assessment_404s_for_another_doctors_donor(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    donor = await create_donor(auth_client, **FULL_RISK_PAYLOAD)

    response = await second_auth_client.get(f"/donors/{donor['id']}/risk-assessment")

    assert response.status_code == 404


async def test_risk_assessment_full_response_shape_when_fully_populated(
    auth_client: AsyncClient,
):
    donor = await create_donor(auth_client, **FULL_RISK_PAYLOAD)

    response = await auth_client.get(f"/donors/{donor['id']}/risk-assessment")

    assert response.status_code == 200
    body = response.json()
    assert body["has_sufficient_data_for_projection"] is True
    assert body["fifteen_year_risk_percent"] is not None
    assert body["lifetime_risk_percent"] is not None
    assert body["relative_risk_multiplier"] is not None
    assert body["age_band_used"] == "35-44"
    assert body["race_used_for_scoring"] == "black"
    assert body["population_validated"] is True
    assert body["race_extrapolation_disclaimer"] is None
    assert body["has_sufficient_data_for_contraindication_screen"] is True
    assert body["has_any_contraindication"] is False
    assert len(body["contraindication_criteria_not_assessed"]) == 3
    assert "Grams" in body["source_citation"]


async def test_risk_assessment_reports_missing_predictors_when_incomplete(
    auth_client: AsyncClient,
):
    donor = await create_donor(auth_client)  # no clinical fields at all

    response = await auth_client.get(f"/donors/{donor['id']}/risk-assessment")

    assert response.status_code == 200
    body = response.json()
    assert body["has_sufficient_data_for_projection"] is False
    assert body["fifteen_year_risk_percent"] is None
    assert set(body["missing_projection_predictors"]) >= {"sex", "race", "egfr"}


async def test_risk_assessment_flags_unvalidated_population_for_other_race(
    auth_client: AsyncClient,
):
    donor = await create_donor(auth_client, **{**FULL_RISK_PAYLOAD, "race": "other"})

    response = await auth_client.get(f"/donors/{donor['id']}/risk-assessment")

    assert response.status_code == 200
    body = response.json()
    assert body["population_validated"] is False
    assert body["race_extrapolation_disclaimer"] is not None
    assert body["race_used_for_scoring"] == "white"

# app/tests/unit/test_donor_risk_service.py
"""The strongest regression oracle here is free: the Grams model's linear
predictor is centered so a donor exactly matching their age band's own
base case yields B == 0, which forces the projected risk to equal the
model's own published Hx exactly (see test_base_case_donor_reproduces_
published_hx_exactly). That's used instead of hand-deriving expected output
numbers for arbitrary inputs."""
from datetime import date

import pytest

from app.reference_data.donor_risk_model import AGE_BANDS, HX_TABLE
from app.services.donor_risk_service import (
    CONTRAINDICATION_REQUIRED_FIELDS,
    PROJECTION_REQUIRED_FIELDS,
    DonorRiskAssessmentInput,
    assess_donor_risk,
    calculate_age_years,
)


def _full_input(**overrides):
    values = dict(
        age_years=40,
        sex="male",
        race="black",
        egfr=98.0,
        systolic_bp=120,
        diastolic_bp=80,
        is_on_antihypertensive_medication=False,
        bmi=26.0,
        has_diabetes=False,
        urine_acr=4.0,
        smoking_status="never",
        family_history_kidney_disease=False,
    )
    values.update(overrides)
    return DonorRiskAssessmentInput(**values)


def _base_case_input(age_band, race, sex):
    """A donor exactly matching `age_band`'s own base case -- every model
    predictor at its centering value, so B == 0 (diastolic_bp/family
    history aren't model predictors, so they're set to unrelated values)."""
    return DonorRiskAssessmentInput(
        age_years=age_band.min_age,
        sex=sex,
        race=race,
        egfr=age_band.base_case_egfr,
        systolic_bp=120,
        diastolic_bp=80,
        is_on_antihypertensive_medication=False,
        bmi=26.0,
        has_diabetes=False,
        urine_acr=4.0,
        smoking_status="never",
        family_history_kidney_disease=None,
    )


def _hx_for(age_band_label, race, sex):
    return next(
        entry
        for entry in HX_TABLE
        if entry.age_band_label == age_band_label and entry.race == race and entry.sex == sex
    )


@pytest.mark.parametrize("age_band", AGE_BANDS, ids=lambda band: band.label)
@pytest.mark.parametrize("race", ["black", "white"])
@pytest.mark.parametrize("sex", ["male", "female"])
def test_base_case_donor_reproduces_published_hx_exactly(age_band, race, sex):
    result = assess_donor_risk(_base_case_input(age_band, race, sex))
    hx = _hx_for(age_band.label, race, sex)

    assert result.has_sufficient_data_for_projection is True
    assert result.linear_predictor == pytest.approx(0.0, abs=1e-9)
    assert result.relative_risk_multiplier == pytest.approx(1.0)
    assert result.fifteen_year_risk_percent == pytest.approx(hx.fifteen_year_percent)
    assert result.lifetime_risk_percent == pytest.approx(hx.lifetime_percent)
    assert result.age_band_used == age_band.label
    assert result.race_used_for_scoring == race


def test_race_other_scores_against_white_and_flags_unvalidated():
    band = AGE_BANDS[2]  # 35-44
    result = assess_donor_risk(_base_case_input(band, "other", "male"))
    white_hx = _hx_for(band.label, "white", "male")

    assert result.race_used_for_scoring == "white"
    assert result.population_validated is False
    assert result.race_extrapolation_disclaimer is not None
    assert result.fifteen_year_risk_percent == pytest.approx(white_hx.fifteen_year_percent)


def test_black_or_white_is_population_validated():
    band = AGE_BANDS[2]
    result = assess_donor_risk(_base_case_input(band, "black", "male"))

    assert result.population_validated is True
    assert result.race_extrapolation_disclaimer is None


def test_in_range_values_are_not_flagged():
    band = AGE_BANDS[2]
    result = assess_donor_risk(_base_case_input(band, "white", "male"))

    assert result.values_outside_model_range == []


def test_egfr_above_top_knot_is_flagged_but_still_projects():
    # Review #2 bug 10: eGFR 200 vs the model's top spline knot of 120 used
    # to silently extrapolate with no warning anywhere.
    band = AGE_BANDS[2]
    result = assess_donor_risk(_full_input(age_years=band.min_age, egfr=200.0))

    assert result.has_sufficient_data_for_projection is True
    assert any("eGFR" in flag for flag in result.values_outside_model_range)


def test_bmi_above_upper_knot_is_flagged():
    result = assess_donor_risk(_full_input(bmi=80.0))

    assert any("BMI" in flag for flag in result.values_outside_model_range)


def test_urine_acr_above_contraindication_ceiling_is_flagged():
    result = assess_donor_risk(_full_input(urine_acr=500.0))

    assert any("ACR" in flag for flag in result.values_outside_model_range)


def test_systolic_bp_above_contraindication_ceiling_is_flagged():
    result = assess_donor_risk(
        _full_input(systolic_bp=180, is_on_antihypertensive_medication=False)
    )

    assert any("Systolic BP" in flag for flag in result.values_outside_model_range)


def test_worse_risk_factors_increase_projected_risk_above_base_case():
    band = AGE_BANDS[2]  # 35-44
    baseline = assess_donor_risk(_base_case_input(band, "white", "male"))
    worse = assess_donor_risk(
        _full_input(
            age_years=band.min_age,
            race="white",
            sex="male",
            egfr=band.base_case_egfr - 20,
            systolic_bp=150,
            is_on_antihypertensive_medication=True,
            bmi=34.0,
            has_diabetes=True,
            urine_acr=50.0,
            smoking_status="current",
        )
    )

    assert worse.relative_risk_multiplier > baseline.relative_risk_multiplier
    assert worse.fifteen_year_risk_percent > baseline.fifteen_year_risk_percent
    assert worse.lifetime_risk_percent > baseline.lifetime_risk_percent


@pytest.mark.parametrize("missing_field", PROJECTION_REQUIRED_FIELDS)
def test_missing_any_projection_predictor_blocks_the_projection(missing_field):
    result = assess_donor_risk(_full_input(**{missing_field: None}))

    assert result.has_sufficient_data_for_projection is False
    assert missing_field in result.missing_projection_predictors
    assert result.fifteen_year_risk_percent is None
    assert result.lifetime_risk_percent is None


@pytest.mark.parametrize("missing_field", CONTRAINDICATION_REQUIRED_FIELDS)
def test_missing_any_contraindication_predictor_blocks_the_screen(missing_field):
    result = assess_donor_risk(_full_input(**{missing_field: None}))

    assert result.has_sufficient_data_for_contraindication_screen is False
    assert missing_field in result.missing_contraindication_predictors
    assert result.contraindications == []


def test_projection_does_not_need_diastolic_bp():
    result = assess_donor_risk(_full_input(diastolic_bp=None))

    assert result.has_sufficient_data_for_projection is True
    assert result.fifteen_year_risk_percent is not None


def test_contraindication_screen_does_not_need_age_sex_race_bmi_smoking():
    result = assess_donor_risk(
        _full_input(age_years=None, sex=None, race=None, bmi=None, smoking_status=None)
    )

    assert result.has_sufficient_data_for_contraindication_screen is True
    assert result.has_sufficient_data_for_projection is False


def test_low_egfr_triggers_contraindication():
    result = assess_donor_risk(_full_input(egfr=40.0))

    assert result.has_any_contraindication is True
    assert any("eGFR" in flag for flag in result.contraindications)


def test_high_urine_acr_triggers_contraindication():
    result = assess_donor_risk(_full_input(urine_acr=350.0))

    assert result.has_any_contraindication is True
    assert any("ACR" in flag for flag in result.contraindications)


def test_high_bp_on_medication_uses_the_lower_threshold():
    result = assess_donor_risk(
        _full_input(systolic_bp=165, diastolic_bp=80, is_on_antihypertensive_medication=True)
    )

    assert result.has_any_contraindication is True


def test_same_bp_without_medication_does_not_trigger_the_lower_threshold():
    result = assess_donor_risk(
        _full_input(systolic_bp=165, diastolic_bp=80, is_on_antihypertensive_medication=False)
    )

    assert result.has_any_contraindication is False


def test_high_bp_without_medication_triggers_the_higher_threshold():
    result = assess_donor_risk(
        _full_input(systolic_bp=175, diastolic_bp=80, is_on_antihypertensive_medication=False)
    )

    assert result.has_any_contraindication is True


def test_no_contraindications_for_a_healthy_donor():
    result = assess_donor_risk(_full_input())

    assert result.has_any_contraindication is False
    assert result.contraindications == []
    assert len(result.contraindication_criteria_not_assessed) == 3


def test_age_outside_supported_range_cannot_be_projected():
    result = assess_donor_risk(_full_input(age_years=90))

    assert result.has_sufficient_data_for_projection is False
    assert result.fifteen_year_risk_percent is None


def test_zero_urine_acr_is_guarded_rather_than_raising():
    result = assess_donor_risk(_full_input(urine_acr=0))

    assert result.has_sufficient_data_for_projection is False
    assert result.fifteen_year_risk_percent is None


def test_diabetes_and_family_history_are_surfaced_as_review_flags_not_gates():
    result = assess_donor_risk(
        _full_input(has_diabetes=True, family_history_kidney_disease=True)
    )

    assert result.diabetes_review_flag is True
    assert result.family_history_flag is True
    # Diabetes is a model predictor (raises the projected risk) but is not,
    # by itself, an automatic contraindication -- see module docstring.
    assert result.has_sufficient_data_for_projection is True


def test_calculate_age_years_handles_birthday_not_yet_reached_this_year():
    assert calculate_age_years(date(1990, 12, 31), as_of=date(2026, 1, 1)) == 35


def test_calculate_age_years_handles_birthday_already_passed_this_year():
    assert calculate_age_years(date(1990, 1, 1), as_of=date(2026, 1, 1)) == 36

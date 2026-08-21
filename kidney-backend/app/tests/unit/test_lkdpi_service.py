# app/tests/unit/test_lkdpi_service.py
import pytest

from app.reference_data.lkdpi_model import REFERENCE_CASE, SOURCE_CITATION, WEIGHT_RATIO_CAP
from app.services.lkdpi_service import (
    FIELD_LABELS,
    REQUIRED_FIELDS,
    LKDPIInput,
    calculate_lkdpi,
)


def _full_input(**overrides):
    values = dict(
        donor_age_years=60,
        donor_egfr=90.0,
        donor_bmi=25.0,
        donor_race="white",
        donor_smoking_status="never",
        donor_systolic_bp=130.0,
        donor_sex="male",
        recipient_sex="female",
        abo_incompatible=False,
        donor_biologically_related=True,
        hla_b_mismatches=1,
        hla_dr_mismatches=1,
        donor_weight_kg=70.0,
        recipient_weight_kg=70.0,
    )
    values.update(overrides)
    return LKDPIInput(**values)


def test_worked_example_matches_hand_calculation():
    """By hand, from app/reference_data/lkdpi_model.py's coefficients:
        age over 50:      1.85 * (60-50)        = +18.500
        eGFR:             -0.381 * 90            = -34.290
        BMI:              1.17 * 25              = +29.250
        African-American: white -> not applied   =   0.000
        Smoking:          never -> not applied    =   0.000
        Systolic BP:      0.44 * 130              = +57.200
        Both male:        male/female -> no       =   0.000
        ABO incompatible: False -> no              =   0.000
        Unrelated:        related=True -> no        =   0.000
        HLA-B:            8.57 * 1                = +8.570
        HLA-DR:           8.26 * 1                = +8.260
        Weight ratio:     -50.87 * min(1.0, 0.9)  = -45.783
        intercept                                  = -11.300
        sum = 18.5 -34.29 +29.25 +57.2 +8.57 +8.26 -45.783 -11.3 = 30.407
    """
    result = calculate_lkdpi(_full_input())

    assert result.has_sufficient_data is True
    assert result.score == pytest.approx(30.41, abs=0.01)
    assert result.band == "moderate"


@pytest.mark.parametrize("field_name", REQUIRED_FIELDS)
def test_missing_input_refuses_rather_than_guesses(field_name):
    result = calculate_lkdpi(_full_input(**{field_name: None}))

    assert result.score is None
    assert result.has_sufficient_data is False
    assert FIELD_LABELS[field_name] in result.missing_inputs


@pytest.mark.parametrize(
    "ratio_inputs",
    [
        {"donor_weight_kg": 90.0, "recipient_weight_kg": 100.0},  # ratio 0.9
        {"donor_weight_kg": 100.0, "recipient_weight_kg": 100.0},  # ratio 1.0
        {"donor_weight_kg": 150.0, "recipient_weight_kg": 100.0},  # ratio 1.5
    ],
)
def test_weight_ratio_caps_at_point_nine(ratio_inputs):
    result = calculate_lkdpi(_full_input(**ratio_inputs))
    weight_contribution = next(
        c for c in result.contributions if c["label"].startswith("Donor/recipient weight ratio")
    )
    # Contribution points are rounded to 2 decimals for display, so compare
    # against that same rounding rather than the raw -45.783.
    assert weight_contribution["points"] == pytest.approx(
        round(-50.87 * WEIGHT_RATIO_CAP, 2), abs=0.01
    )


def test_age_hinge_at_and_below_fifty_contributes_zero():
    for age in (50, 45):
        result = calculate_lkdpi(_full_input(donor_age_years=age))
        age_term = next(
            c for c in result.contributions if c["label"].startswith("Donor age over 50")
        )
        assert age_term["points"] == 0.0


def test_age_hinge_above_fifty_contributes_correctly():
    result = calculate_lkdpi(_full_input(donor_age_years=60))
    age_term = next(c for c in result.contributions if c["label"].startswith("Donor age over 50"))
    assert age_term["points"] == pytest.approx(18.5, abs=0.001)


def test_race_other_is_not_population_validated():
    result = calculate_lkdpi(_full_input(donor_race="other"))
    assert result.population_validated is False
    assert result.population_extrapolation_disclaimer is not None


@pytest.mark.parametrize("race", ["black", "white"])
def test_race_black_or_white_is_population_validated(race):
    result = calculate_lkdpi(_full_input(donor_race=race))
    assert result.population_validated is True
    assert result.population_extrapolation_disclaimer is None


def test_donor_african_american_gets_the_race_term():
    baseline = calculate_lkdpi(_full_input(donor_race="white"))
    black = calculate_lkdpi(_full_input(donor_race="black"))
    assert black.score == pytest.approx(baseline.score + 22.34, abs=0.001)


def test_contributions_sum_to_score_minus_intercept():
    result = calculate_lkdpi(_full_input())
    total_contribution_points = sum(c["points"] for c in result.contributions)
    # intercept is -11.30 and not itself a "contribution" entry.
    assert total_contribution_points == pytest.approx(result.score - (-11.30), abs=0.01)


def _reference_equivalent_input(**overrides):
    """Every term evaluates identically to LKDPIReferenceCase -- i.e. every
    delta is 0 -- unless overridden. Used to isolate the single-factor
    override's behaviour to exactly the term(s) being deliberately pushed
    away from baseline, independent of the (large, by-construction) raw
    magnitude of every continuous term."""
    values = dict(
        donor_age_years=REFERENCE_CASE.donor_age_years,
        donor_egfr=REFERENCE_CASE.donor_egfr,
        donor_bmi=REFERENCE_CASE.donor_bmi,
        donor_race="white",  # not African-American, matches REFERENCE_CASE
        donor_smoking_status="never",
        donor_systolic_bp=REFERENCE_CASE.donor_systolic_bp,
        donor_sex="male",
        recipient_sex="female",  # not both male, matches REFERENCE_CASE
        abo_incompatible=REFERENCE_CASE.abo_incompatible,
        donor_biologically_related=not REFERENCE_CASE.biologically_unrelated,
        hla_b_mismatches=REFERENCE_CASE.hla_b_mismatches,
        hla_dr_mismatches=REFERENCE_CASE.hla_dr_mismatches,
        donor_weight_kg=90.0,
        recipient_weight_kg=100.0,  # ratio 0.9, matches REFERENCE_CASE.weight_ratio
    )
    values.update(overrides)
    return LKDPIInput(**values)


def test_no_single_factor_override_for_a_typical_donor():
    # E7.1 regression: an otherwise-ideal donor (age 35, eGFR 100, BMI 23,
    # SBP 118, never-smoker, related, 0/0 mismatches, weight ratio 0.86)
    # used to trip the override on 3 separate terms under the old
    # raw-magnitude check (every continuous term is large by construction,
    # so it fired on nearly every real donor) -- fixed by comparing each
    # term's deviation from LKDPIReferenceCase instead. This donor should
    # score well (excellent/good) and get no override at all.
    result = calculate_lkdpi(
        _full_input(
            donor_age_years=35,
            donor_egfr=100.0,
            donor_bmi=23.0,
            donor_systolic_bp=118.0,
            donor_smoking_status="never",
            donor_biologically_related=True,
            hla_b_mismatches=0,
            hla_dr_mismatches=0,
            donor_weight_kg=86.0,
            recipient_weight_kg=100.0,
        )
    )
    assert result.single_factor_override is None


def test_single_factor_override_fires_on_deviation_from_reference_case():
    # Every other term held exactly at LKDPIReferenceCase (delta 0);
    # systolic BP alone pushed to 160 -> delta = 0.44*(160-120) = +17.6,
    # past SINGLE_FACTOR_OVERRIDE_THRESHOLD (15.0) -- the exact worked
    # example from the implementation prompt's E7.1.
    result = calculate_lkdpi(_reference_equivalent_input(donor_systolic_bp=160.0))
    assert result.single_factor_override is not None
    assert result.single_factor_override["label"].startswith("Donor systolic BP")
    assert result.single_factor_override["delta"] == pytest.approx(17.6, abs=0.01)


def test_no_override_when_every_term_matches_reference_case():
    result = calculate_lkdpi(_reference_equivalent_input())
    assert result.single_factor_override is None
    assert all(c["delta"] == pytest.approx(0.0, abs=0.001) for c in result.contributions)


def test_range_warnings_are_flagged_not_clamped():
    result = calculate_lkdpi(
        _full_input(donor_egfr=10.0, donor_bmi=50.0, donor_systolic_bp=200.0, donor_age_years=90)
    )
    assert result.has_sufficient_data is True  # still computed, just flagged
    assert any("eGFR" in flag for flag in result.values_outside_model_range)
    assert any("BMI" in flag for flag in result.values_outside_model_range)
    assert any("systolic BP" in flag for flag in result.values_outside_model_range)
    assert any("age" in flag for flag in result.values_outside_model_range)


def test_in_range_values_are_not_flagged():
    result = calculate_lkdpi(_full_input())
    assert result.values_outside_model_range == []


def test_source_citation_is_present():
    result = calculate_lkdpi(_full_input())
    assert result.source_citation == SOURCE_CITATION

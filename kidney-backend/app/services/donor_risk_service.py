# app/services/donor_risk_service.py
"""
Donor safety assessment: "is it safe for this person to donate a kidney?",
answered on its own, independent of any recipient. Implements the Grams et
al. (NEJM 2016) living-kidney-donor-candidate ESRD risk projection -- see
app/reference_data/donor_risk_model.py for the model itself, its exact
source, and its validated-population limitations (read that module's
docstring before touching this one).

Two independent questions, each with its own data-sufficiency gate, not one
combined pipeline:
1. Absolute contraindications (appendix Section 3 Step 1) -- hard exclusion
   criteria the model's own authors used to define a "low-risk" reference
   population. This app can only check 3 of the paper's 6 criteria; the
   other 3 are named in the result, not silently dropped. Diastolic BP is a
   contraindication-only input -- it is never a term in the projection's own
   linear predictor below.
2. Quantitative projection (appendix Section 4) -- 15-year and lifetime
   projected ESRD incidence in the ABSENCE of donation, plus a
   relative-risk multiplier, for a donor with no contraindication.

Missing data is surfaced, never guessed -- matching this codebase's existing
services (PRABucketResult.has_sufficient_data, MismatchResult's worst-casing
for missing HLA typing). This module never imports app.models/app.schemas:
like the other pure scoring services (dsa_service.py, pra_bucket_service.py,
abo_service.py), it takes and returns plain dataclasses so it stays testable
without a database and reusable outside the API layer.
"""

import math
from dataclasses import dataclass, field
from datetime import date

from app.reference_data.donor_risk_model import (
    AGE_BANDS,
    BASE_CASE_ACR,
    BASE_CASE_BMI,
    BASE_CASE_SBP,
    COEFFICIENTS,
    CONTRAINDICATION_ACR_CEILING,
    CONTRAINDICATION_DBP_WITH_MEDICATION,
    CONTRAINDICATION_DBP_WITHOUT_MEDICATION,
    CONTRAINDICATION_EGFR_FLOOR,
    CONTRAINDICATION_SBP_WITH_MEDICATION,
    CONTRAINDICATION_SBP_WITHOUT_MEDICATION,
    EGFR_KNOT_HIGH,
    EGFR_KNOT_LOW,
    EGFR_KNOT_MID,
    GENERAL_POPULATION_DISCLAIMER,
    HX_TABLE,
    OTHER_RACE_EXTRAPOLATION_DISCLAIMER,
    RACE_FOR_SCORING,
    SOURCE_CITATION,
    AgeBand,
)

# BMI's upper spline knot -- see _spline_bmi. Not imported from
# donor_risk_model.py since (unlike EGFR_KNOT_HIGH/CONTRAINDICATION_*) it
# isn't itself a named reference-data constant there, just the literal `30`
# baked into the spline formula; named here so _values_outside_model_range
# below states its reasoning once rather than repeating the bare number.
_BMI_UPPER_KNOT = 30.0

# The projection's own linear predictor never reads diastolic_bp -- see
# module docstring. Keeping the two gates' required-field lists separate
# (rather than one combined list) is deliberate: a donor missing only
# diastolic_bp can still get a full quantitative projection, and a donor
# missing only urine_acr can still get a full contraindication screen.
PROJECTION_REQUIRED_FIELDS = (
    "age_years",
    "sex",
    "race",
    "egfr",
    "systolic_bp",
    "is_on_antihypertensive_medication",
    "bmi",
    "has_diabetes",
    "urine_acr",
    "smoking_status",
)

CONTRAINDICATION_REQUIRED_FIELDS = (
    "egfr",
    "systolic_bp",
    "diastolic_bp",
    "is_on_antihypertensive_medication",
    "urine_acr",
)

CONTRAINDICATION_CRITERIA_NOT_ASSESSED = (
    "Insulin-dependent diabetes (this app records diabetes as yes/no only, "
    "not insulin dependence)",
    "Use of 4 or more antihypertensive medications (this app records use "
    "as yes/no only, not a count)",
    "History of coronary heart disease, stroke, congestive heart failure, "
    "or peripheral arterial disease (not captured by this app)",
)


@dataclass
class DonorRiskAssessmentInput:
    age_years: int | None
    sex: str | None  # "male" | "female"
    race: str | None  # "black" | "white" | "other"
    egfr: float | None
    systolic_bp: int | None
    diastolic_bp: int | None
    is_on_antihypertensive_medication: bool | None
    bmi: float | None
    has_diabetes: bool | None
    urine_acr: float | None
    smoking_status: str | None  # "never" | "former" | "current"
    family_history_kidney_disease: bool | None


@dataclass
class DonorRiskAssessmentResult:
    has_sufficient_data_for_projection: bool
    missing_projection_predictors: list[str] = field(default_factory=list)
    fifteen_year_risk_percent: float | None = None
    lifetime_risk_percent: float | None = None
    relative_risk_multiplier: float | None = None  # exp(B) vs. this donor's own base case
    linear_predictor: float | None = None  # B, kept for transparency/debugging
    age_band_used: str | None = None
    race_used_for_scoring: str | None = None  # "black" | "white" -- the row actually applied

    has_sufficient_data_for_contraindication_screen: bool = False
    missing_contraindication_predictors: list[str] = field(default_factory=list)
    contraindications: list[str] = field(default_factory=list)
    has_any_contraindication: bool = False
    contraindication_criteria_not_assessed: list[str] = field(
        default_factory=lambda: list(CONTRAINDICATION_CRITERIA_NOT_ASSESSED)
    )

    # Review #2 bug 15: has_diabetes IS a scored linear-predictor term
    # (COEFFICIENTS.diabetes, applied in _linear_predictor above) --
    # surfaced here *in addition* to that, not instead of it, so a
    # clinician sees it as its own flag alongside the quantitative
    # projection it already contributed to (rather than mentally adding
    # extra risk on top of a number that already contains it).
    # family_history_kidney_disease, by contrast, really isn't a model
    # predictor at all -- donor_risk_service.py never reads it for the
    # calculation, only surfaces it here for a clinician's own judgment,
    # same posture as the rest of this app's "informational, not gating"
    # clinical fields.
    diabetes_review_flag: bool | None = None
    family_history_flag: bool | None = None

    population_validated: bool = True
    general_disclaimer: str = GENERAL_POPULATION_DISCLAIMER
    race_extrapolation_disclaimer: str | None = None
    source_citation: str = SOURCE_CITATION

    # Review #2 bug 10: age is the only predictor that was ever refused a
    # projection for being out of range (see age_band handling below) --
    # eGFR/BMI/ACR/SBP could all be typed arbitrarily high and the spline
    # would silently extrapolate linearly past the range the model's own
    # authors actually validated, with no warning anywhere (e.g. eGFR 200
    # vs the model's top knot of 120 -> a confident-looking 3.5x relative
    # risk built on zero real data). A soft flag, not a block, like
    # race_extrapolation_disclaimer -- the projection still computes (a
    # clinician may still want *a* number), it's just labeled as
    # extrapolated beyond validated support.
    values_outside_model_range: list[str] = field(default_factory=list)


def calculate_age_years(date_of_birth: date, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    age = as_of.year - date_of_birth.year
    if (as_of.month, as_of.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    return age


def _find_age_band(age_years: int) -> AgeBand | None:
    for band in AGE_BANDS:
        if band.min_age <= age_years <= band.max_age:
            return band
    return None


def _missing_fields(data: DonorRiskAssessmentInput, required: tuple[str, ...]) -> list[str]:
    return [name for name in required if getattr(data, name) is None]


def _spline_egfr(egfr: float, egfr_base: float) -> tuple[float, float, float, float]:
    egfr1 = (EGFR_KNOT_LOW - min(egfr, EGFR_KNOT_LOW)) / 15
    egfr2 = (min(egfr_base, EGFR_KNOT_MID) - max(min(egfr, EGFR_KNOT_MID), EGFR_KNOT_LOW)) / 15
    egfr3 = (max(egfr_base, EGFR_KNOT_MID) - max(min(egfr, EGFR_KNOT_HIGH), EGFR_KNOT_MID)) / 15
    egfr4 = (EGFR_KNOT_HIGH - max(egfr, EGFR_KNOT_HIGH)) / 15
    return egfr1, egfr2, egfr3, egfr4


def _spline_bmi(bmi: float) -> tuple[float, float]:
    # bmi1's cap must match bmi2's knot (30) exactly -- both used to
    # disagree (bmi1 capped at BMI 31, bmi2's knot was 30), so between
    # BMI 30 and 31 both terms were simultaneously active and increasing,
    # a spurious third segment the two-knot linear spline was never meant
    # to have (~0.5% effect on the projection). Fixed 2026-08-09 (review
    # #2 bug 14).
    bmi1 = min(bmi - BASE_CASE_BMI, 4) / 5
    bmi2 = max(bmi - 30, 0) / 5
    return bmi1, bmi2


def _linear_predictor(
    *,
    egfr: float,
    egfr_base: float,
    systolic_bp: float,
    is_on_antihypertensive_medication: bool,
    bmi: float,
    has_diabetes: bool,
    urine_acr: float,
    smoking_status: str,
) -> float:
    """Appendix Sections 3-4, Step "Calculate linear function ... using
    meta-analyzed beta coefficients (Table 2)". Centered so a donor exactly
    matching their age band's base case yields B == 0 -- see
    test_donor_risk_service.py's base-case-identity tests, which rely on
    that property as their regression oracle instead of hand-derived
    expected values."""
    egfr1, egfr2, egfr3, egfr4 = _spline_egfr(egfr, egfr_base)
    bmi1, bmi2 = _spline_bmi(bmi)

    return (
        COEFFICIENTS.egfr1 * egfr1
        + COEFFICIENTS.egfr2 * egfr2
        + COEFFICIENTS.egfr3 * egfr3
        + COEFFICIENTS.egfr4 * egfr4
        + COEFFICIENTS.sbp_per_20mmhg * (systolic_bp - BASE_CASE_SBP) / 20
        + (
            COEFFICIENTS.antihypertensive_medication
            if is_on_antihypertensive_medication
            else 0.0
        )
        + COEFFICIENTS.bmi1 * bmi1
        + COEFFICIENTS.bmi2 * bmi2
        + (COEFFICIENTS.diabetes if has_diabetes else 0.0)
        + COEFFICIENTS.log10_acr * (math.log10(urine_acr) - math.log10(BASE_CASE_ACR))
        + (COEFFICIENTS.former_smoker if smoking_status == "former" else 0.0)
        + (COEFFICIENTS.current_smoker if smoking_status == "current" else 0.0)
    )


def _project_risk(hx_percent: float, linear_predictor: float) -> float:
    """Appendix Section 4 Step 5: Risk% = (1 - (1 - Hx/100)^exp(B)) * 100."""
    return (1 - (1 - hx_percent / 100) ** math.exp(linear_predictor)) * 100


def _values_outside_model_range(data: DonorRiskAssessmentInput) -> list[str]:
    """Flags predictors whose value falls outside the range the model's
    own reference population actually supports -- reusing the ceilings the
    paper's authors already used to define that population (the
    contraindication thresholds) rather than inventing new, unreviewed
    numbers. Only called once age has already been confirmed in-range (see
    assess_donor_risk), so this only needs to cover the four predictors
    that had no such check at all: eGFR, BMI, urine ACR, systolic BP.
    Diastolic BP is excluded on purpose -- the projection's linear
    predictor never reads it (see module docstring)."""
    flags: list[str] = []

    if data.egfr > EGFR_KNOT_HIGH:
        flags.append(
            f"eGFR {data.egfr} mL/min/1.73m² is above the model's top spline knot "
            f"({EGFR_KNOT_HIGH:.0f}) -- this projection is a linear extrapolation "
            "beyond the range the model was fit on, not an interpolated value."
        )

    if data.bmi > _BMI_UPPER_KNOT:
        flags.append(
            f"BMI {data.bmi} is above the model's upper spline knot "
            f"({_BMI_UPPER_KNOT:.0f}) -- extrapolated, not interpolated."
        )

    if data.urine_acr >= CONTRAINDICATION_ACR_CEILING:
        flags.append(
            f"Urine ACR {data.urine_acr} mg/g is at or above "
            f"{CONTRAINDICATION_ACR_CEILING:.0f} mg/g, the macroalbuminuria "
            "threshold the model's authors used to define their reference "
            "population -- extrapolated beyond it."
        )

    on_medication = bool(data.is_on_antihypertensive_medication)
    sbp_ceiling = (
        CONTRAINDICATION_SBP_WITH_MEDICATION
        if on_medication
        else CONTRAINDICATION_SBP_WITHOUT_MEDICATION
    )
    if data.systolic_bp >= sbp_ceiling:
        flags.append(
            f"Systolic BP {data.systolic_bp} mmHg is at or above {sbp_ceiling} mmHg "
            f"({'on' if on_medication else 'not on'} antihypertensive medication), "
            "the threshold the model's authors used to define their reference "
            "population -- extrapolated beyond it."
        )

    return flags


def _find_hx_entry(age_band_label: str, race: str, sex: str):
    for entry in HX_TABLE:
        if entry.age_band_label == age_band_label and entry.race == race and entry.sex == sex:
            return entry
    raise ValueError(
        f"No base-case Hx entry for {age_band_label}/{race}/{sex} -- HX_TABLE is incomplete"
    )


def _screen_contraindications(
    data: DonorRiskAssessmentInput,
) -> tuple[bool, list[str], list[str], bool]:
    """Returns (has_sufficient_data, missing_predictors, contraindications, has_any)."""
    missing = _missing_fields(data, CONTRAINDICATION_REQUIRED_FIELDS)
    if missing:
        return False, missing, [], False

    flags: list[str] = []

    if data.egfr < CONTRAINDICATION_EGFR_FLOOR:
        flags.append(
            f"eGFR {data.egfr} mL/min/1.73m² is below the "
            f"{CONTRAINDICATION_EGFR_FLOOR:.0f} floor used to define the model's own "
            "low-risk reference population."
        )

    if data.urine_acr >= CONTRAINDICATION_ACR_CEILING:
        flags.append(
            f"Urine ACR {data.urine_acr} mg/g is at or above the "
            f"{CONTRAINDICATION_ACR_CEILING:.0f} mg/g macroalbuminuria threshold."
        )

    on_medication = bool(data.is_on_antihypertensive_medication)
    sbp_ceiling = (
        CONTRAINDICATION_SBP_WITH_MEDICATION
        if on_medication
        else CONTRAINDICATION_SBP_WITHOUT_MEDICATION
    )
    dbp_ceiling = (
        CONTRAINDICATION_DBP_WITH_MEDICATION
        if on_medication
        else CONTRAINDICATION_DBP_WITHOUT_MEDICATION
    )
    if data.systolic_bp >= sbp_ceiling or data.diastolic_bp >= dbp_ceiling:
        flags.append(
            f"Blood pressure {data.systolic_bp}/{data.diastolic_bp} mmHg is at or above "
            f"{sbp_ceiling}/{dbp_ceiling} mmHg while "
            f"{'on' if on_medication else 'not on'} antihypertensive medication."
        )

    return True, [], flags, bool(flags)


def assess_donor_risk(data: DonorRiskAssessmentInput) -> DonorRiskAssessmentResult:
    (
        has_contra_data,
        missing_contra,
        contraindications,
        has_any_contraindication,
    ) = _screen_contraindications(data)

    missing_projection = _missing_fields(data, PROJECTION_REQUIRED_FIELDS)
    age_band = None if missing_projection else _find_age_band(data.age_years)
    if not missing_projection and age_band is None:
        missing_projection = [
            f"age {data.age_years} is outside the model's supported 15-84 range"
        ]
    if not missing_projection and data.urine_acr <= 0:
        missing_projection = ["urine_acr must be greater than 0 to be projected"]

    if missing_projection:
        return DonorRiskAssessmentResult(
            has_sufficient_data_for_projection=False,
            missing_projection_predictors=missing_projection,
            has_sufficient_data_for_contraindication_screen=has_contra_data,
            missing_contraindication_predictors=missing_contra,
            contraindications=contraindications,
            has_any_contraindication=has_any_contraindication,
            diabetes_review_flag=data.has_diabetes,
            family_history_flag=data.family_history_kidney_disease,
        )

    linear_predictor = _linear_predictor(
        egfr=data.egfr,
        egfr_base=age_band.base_case_egfr,
        systolic_bp=data.systolic_bp,
        is_on_antihypertensive_medication=bool(data.is_on_antihypertensive_medication),
        bmi=data.bmi,
        has_diabetes=bool(data.has_diabetes),
        urine_acr=data.urine_acr,
        smoking_status=data.smoking_status,
    )
    race_for_scoring = RACE_FOR_SCORING[data.race]
    hx_entry = _find_hx_entry(age_band.label, race_for_scoring, data.sex)
    population_validated = data.race != "other"

    return DonorRiskAssessmentResult(
        has_sufficient_data_for_projection=True,
        fifteen_year_risk_percent=_project_risk(hx_entry.fifteen_year_percent, linear_predictor),
        lifetime_risk_percent=_project_risk(hx_entry.lifetime_percent, linear_predictor),
        relative_risk_multiplier=math.exp(linear_predictor),
        linear_predictor=linear_predictor,
        age_band_used=age_band.label,
        race_used_for_scoring=race_for_scoring,
        has_sufficient_data_for_contraindication_screen=has_contra_data,
        missing_contraindication_predictors=missing_contra,
        contraindications=contraindications,
        has_any_contraindication=has_any_contraindication,
        diabetes_review_flag=data.has_diabetes,
        family_history_flag=data.family_history_kidney_disease,
        population_validated=population_validated,
        race_extrapolation_disclaimer=(
            None if population_validated else OTHER_RACE_EXTRAPOLATION_DISCLAIMER
        ),
        values_outside_model_range=_values_outside_model_range(data),
    )

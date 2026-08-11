# app/services/lkdpi_service.py
"""
LKDPI: "how good is this kidney, for this recipient?" -- answered only once
the pairing itself is viable (see match_pipeline.py, which never computes
this for a halted report). Implements Massie et al. (AJT 2016) -- see
app/reference_data/lkdpi_model.py for the model itself, its exact source,
and its validated-population limitations (read that module's docstring
before touching this one).

This is a *comparative* index (see lkdpi_model.py's docstring on the paper's
own stated purpose), deliberately kept separate from the verdict
(app/reference_data/report_outcome.py): ABO incompatibility and a positive
crossmatch are hard biological gates handled entirely upstream, not
probabilities this module could ever soften or override.

Missing data is refused, never guessed -- the single most important
behaviour here, matching donor_risk_service.py's DonorRiskAssessmentResult
contract. If any of the model's inputs is None, this returns score=None and
names every missing field; it never substitutes a default, a mean, or zero.
This module never imports app.models/app.schemas, same as the other pure
scoring services (dsa_service.py, pra_bucket_service.py, donor_risk_
service.py), so it stays testable without a database.
"""

from dataclasses import dataclass, field
from typing import Optional

from app.reference_data.lkdpi_model import (
    BMI_RANGE,
    COEFFICIENTS,
    DONOR_AGE_RANGE,
    EGFR_RANGE,
    LKDPI_BANDS,
    MODEL_LIMITATION_NOTE,
    POPULATION_EXTRAPOLATION_DISCLAIMER,
    POPULATION_VALIDATED_RACES,
    REFERENCE_CASE,
    SINGLE_FACTOR_OVERRIDE_THRESHOLD,
    SOURCE_CITATION,
    SYSTOLIC_BP_RANGE,
    WEIGHT_RATIO_CAP,
    WEIGHT_RATIO_RANGE,
)

# Every physical data point the formula needs. Two of the paper's 13 terms
# (weight ratio, "both male") each need two of these, which is why this list
# runs slightly longer than "13" -- see lkdpi_model.py's docstring.
REQUIRED_FIELDS = (
    "donor_age_years",
    "donor_egfr",
    "donor_bmi",
    "donor_race",
    "donor_smoking_status",
    "donor_systolic_bp",
    "donor_sex",
    "recipient_sex",
    "abo_incompatible",
    "donor_biologically_related",
    "hla_b_mismatches",
    "hla_dr_mismatches",
    "donor_weight_kg",
    "recipient_weight_kg",
)

# Human-readable names for missing_inputs / range warnings -- kept here
# rather than in the frontend so backend and any future consumer (a report
# PDF, an API client) see the same wording.
FIELD_LABELS: dict[str, str] = {
    "donor_age_years": "donor age",
    "donor_egfr": "donor eGFR",
    "donor_bmi": "donor BMI",
    "donor_race": "donor race",
    "donor_smoking_status": "donor smoking status",
    "donor_systolic_bp": "donor systolic BP",
    "donor_sex": "donor sex",
    "recipient_sex": "recipient sex",
    "abo_incompatible": "ABO compatibility result",
    "donor_biologically_related": "donor biological relationship to recipient",
    "hla_b_mismatches": "HLA-B mismatch count",
    "hla_dr_mismatches": "HLA-DR mismatch count",
    "donor_weight_kg": "donor weight",
    "recipient_weight_kg": "recipient weight",
}


@dataclass
class LKDPIInput:
    donor_age_years: Optional[int]
    donor_egfr: Optional[float]
    donor_bmi: Optional[float]
    donor_race: Optional[str]  # "black" | "white" | "other"
    donor_smoking_status: Optional[str]  # "never" | "former" | "current"
    donor_systolic_bp: Optional[float]
    donor_sex: Optional[str]  # "male" | "female"
    recipient_sex: Optional[str]  # "male" | "female"
    abo_incompatible: Optional[bool]
    donor_biologically_related: Optional[bool]
    hla_b_mismatches: Optional[int]
    hla_dr_mismatches: Optional[int]
    donor_weight_kg: Optional[float]
    recipient_weight_kg: Optional[float]


@dataclass
class LKDPIResult:
    score: Optional[float]
    band: Optional[str]
    band_label: Optional[str]
    has_sufficient_data: bool
    missing_inputs: list[str] = field(default_factory=list)
    contributions: list[dict] = field(default_factory=list)
    values_outside_model_range: list[str] = field(default_factory=list)
    population_validated: bool = True
    population_extrapolation_disclaimer: Optional[str] = None
    model_limitation_note: str = MODEL_LIMITATION_NOTE
    source_citation: str = SOURCE_CITATION
    # NEWS2-style override (lkdpi_model.SINGLE_FACTOR_OVERRIDE_THRESHOLD):
    # the single largest-magnitude contribution when it alone exceeds the
    # threshold, regardless of whether the total looks fine.
    single_factor_override: Optional[dict] = None


def _missing_fields(data: LKDPIInput) -> list[str]:
    missing = []
    for name in REQUIRED_FIELDS:
        if getattr(data, name) is None:
            missing.append(FIELD_LABELS[name])
    return missing


def _reference_term_points() -> list[float]:
    """The same 12-term computation calculate_lkdpi runs below, evaluated
    against LKDPIReferenceCase instead of a real donor -- in this exact
    term order, so zip(terms, _reference_term_points()) lines up
    positionally. Only ever consumed for the single-factor-override delta;
    never substituted into an actual score (see REFERENCE_CASE's
    docstring)."""
    ref = REFERENCE_CASE
    ref_age_over_50 = max(ref.donor_age_years - 50, 0)
    return [
        COEFFICIENTS.donor_age_over_50_per_year * ref_age_over_50,
        COEFFICIENTS.donor_egfr * ref.donor_egfr,
        COEFFICIENTS.donor_bmi * ref.donor_bmi,
        COEFFICIENTS.donor_african_american if ref.donor_african_american else 0.0,
        COEFFICIENTS.donor_ever_smoked if ref.donor_ever_smoked else 0.0,
        COEFFICIENTS.donor_systolic_bp * ref.donor_systolic_bp,
        COEFFICIENTS.both_male if ref.both_male else 0.0,
        COEFFICIENTS.abo_incompatible if ref.abo_incompatible else 0.0,
        COEFFICIENTS.biologically_unrelated if ref.biologically_unrelated else 0.0,
        COEFFICIENTS.hla_b_mismatch * ref.hla_b_mismatches,
        COEFFICIENTS.hla_dr_mismatch * ref.hla_dr_mismatches,
        COEFFICIENTS.weight_ratio_capped * min(ref.weight_ratio, WEIGHT_RATIO_CAP),
    ]


def _band_for_score(score: float) -> tuple[str, str]:
    for band in LKDPI_BANDS:
        if band.upper_bound is None or score < band.upper_bound:
            return band.name, band.label
    # Unreachable: the last band in LKDPI_BANDS always has upper_bound=None.
    raise AssertionError("LKDPI_BANDS is missing a catch-all top band")


def _values_outside_model_range(data: LKDPIInput, weight_ratio: float) -> list[str]:
    flags: list[str] = []

    egfr_low, egfr_high = EGFR_RANGE
    if not (egfr_low <= data.donor_egfr <= egfr_high):
        flags.append(
            f"Donor eGFR {data.donor_egfr} mL/min/1.73m^2 is outside the "
            f"{egfr_low:.0f}-{egfr_high:.0f} range this model's inputs were checked against."
        )

    bmi_low, bmi_high = BMI_RANGE
    if not (bmi_low <= data.donor_bmi <= bmi_high):
        flags.append(
            f"Donor BMI {data.donor_bmi} is outside the {bmi_low:.0f}-{bmi_high:.0f} "
            "range this model's inputs were checked against."
        )

    sbp_low, sbp_high = SYSTOLIC_BP_RANGE
    if not (sbp_low <= data.donor_systolic_bp <= sbp_high):
        flags.append(
            f"Donor systolic BP {data.donor_systolic_bp} mmHg is outside the "
            f"{sbp_low:.0f}-{sbp_high:.0f} range this model's inputs were checked against."
        )

    age_low, age_high = DONOR_AGE_RANGE
    if not (age_low <= data.donor_age_years <= age_high):
        flags.append(
            f"Donor age {data.donor_age_years} is outside the {age_low}-{age_high} "
            "range this model's inputs were checked against."
        )

    ratio_low, ratio_high = WEIGHT_RATIO_RANGE
    if not (ratio_low <= weight_ratio <= ratio_high):
        flags.append(
            f"Donor/recipient weight ratio {weight_ratio:.2f} is outside the "
            f"{ratio_low}-{ratio_high} range this model's inputs were checked against."
        )

    return flags


def calculate_lkdpi(data: LKDPIInput) -> LKDPIResult:
    missing = _missing_fields(data)
    if missing:
        return LKDPIResult(
            score=None,
            band=None,
            band_label=None,
            has_sufficient_data=False,
            missing_inputs=missing,
        )

    donor_ever_smoked = data.donor_smoking_status in ("former", "current")
    donor_african_american = data.donor_race == "black"
    both_male = data.donor_sex == "male" and data.recipient_sex == "male"
    biologically_unrelated = not data.donor_biologically_related
    weight_ratio = data.donor_weight_kg / data.recipient_weight_kg
    capped_weight_ratio = min(weight_ratio, WEIGHT_RATIO_CAP)

    age_over_50 = max(data.donor_age_years - 50, 0)

    terms = [
        (
            f"Donor age over 50 ({data.donor_age_years})",
            COEFFICIENTS.donor_age_over_50_per_year * age_over_50,
        ),
        (f"Donor eGFR ({data.donor_egfr})", COEFFICIENTS.donor_egfr * data.donor_egfr),
        (f"Donor BMI ({data.donor_bmi})", COEFFICIENTS.donor_bmi * data.donor_bmi),
        (
            "Donor race (African-American)",
            COEFFICIENTS.donor_african_american if donor_african_american else 0.0,
        ),
        (
            f"Donor smoking history ({data.donor_smoking_status})",
            COEFFICIENTS.donor_ever_smoked if donor_ever_smoked else 0.0,
        ),
        (
            f"Donor systolic BP ({data.donor_systolic_bp} mmHg)",
            COEFFICIENTS.donor_systolic_bp * data.donor_systolic_bp,
        ),
        (
            "Donor and recipient both male",
            COEFFICIENTS.both_male if both_male else 0.0,
        ),
        (
            "ABO incompatible",
            COEFFICIENTS.abo_incompatible if data.abo_incompatible else 0.0,
        ),
        (
            "Biologically unrelated donor",
            COEFFICIENTS.biologically_unrelated if biologically_unrelated else 0.0,
        ),
        (
            f"HLA-B mismatches ({data.hla_b_mismatches})",
            COEFFICIENTS.hla_b_mismatch * data.hla_b_mismatches,
        ),
        (
            f"HLA-DR mismatches ({data.hla_dr_mismatches})",
            COEFFICIENTS.hla_dr_mismatch * data.hla_dr_mismatches,
        ),
        (
            f"Donor/recipient weight ratio ({weight_ratio:.2f}, capped at {WEIGHT_RATIO_CAP})",
            COEFFICIENTS.weight_ratio_capped * capped_weight_ratio,
        ),
    ]

    score = COEFFICIENTS.intercept + sum(points for _, points in terms)
    band_name, band_label = _band_for_score(score)

    # (b) from E7.2: the intercept is deliberately NOT a term here, so bars
    # sum to (score - intercept), not score -- an intercept isn't a
    # clinical driver and has no business in a "what moved this score"
    # breakdown. Frontend labels this block accordingly.
    reference_points = _reference_term_points()
    deltas = [points - reference_points[idx] for idx, (_, points) in enumerate(terms)]

    contributions = sorted(
        (
            {"label": label, "points": round(points, 2), "delta": round(delta, 2)}
            for (label, points), delta in zip(terms, deltas)
        ),
        key=lambda c: abs(c["points"]),
        reverse=True,
    )

    # E7.1: fires on deviation from REFERENCE_CASE, not on raw magnitude --
    # a continuous term (eGFR, SBP, weight ratio...) is large by
    # construction, so comparing its raw points against a flat threshold
    # flagged nearly every donor regardless of how typical they actually
    # were. See LKDPIReferenceCase's docstring.
    single_factor_override = None
    if contributions:
        by_delta = max(contributions, key=lambda c: abs(c["delta"]))
        if abs(by_delta["delta"]) > SINGLE_FACTOR_OVERRIDE_THRESHOLD:
            single_factor_override = by_delta

    population_validated = data.donor_race in POPULATION_VALIDATED_RACES

    return LKDPIResult(
        score=round(score, 2),
        band=band_name,
        band_label=band_label,
        has_sufficient_data=True,
        contributions=contributions,
        values_outside_model_range=_values_outside_model_range(data, weight_ratio),
        population_validated=population_validated,
        population_extrapolation_disclaimer=(
            None if population_validated else POPULATION_EXTRAPOLATION_DISCLAIMER
        ),
        single_factor_override=single_factor_override,
    )

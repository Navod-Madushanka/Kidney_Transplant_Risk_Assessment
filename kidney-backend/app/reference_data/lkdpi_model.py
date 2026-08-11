# app/reference_data/lkdpi_model.py
"""
Massie ME, Leanza J, Fahmy LM, et al. "A Risk Index for Living Donor Kidney
Transplantation." Am J Transplant 2016;16(7):2077-2084. DOI:
10.1111/ajt.13709. The Living Kidney Donor Profile Index (LKDPI) -- the
living-donor analogue of the deceased-donor KDPI, deliberately placed on the
same scale so an LKDPI of 20 reads as "expected risk equivalent to a
deceased donor with KDPI 20."

Every coefficient below was checked directly against the paper's own
full-text formula (PMC6114098, the NIH PubMed Central mirror -- not a
secondary summary or a hand-reconstructed formula) on 2026-08-10: the
article states the LKDPI equation verbatim, and all 13 terms here match it
exactly. If these numbers are ever revisited, re-check them against that
full text (or the publisher's own PDF) directly rather than trust this file
or any other relay of it.

This is a *comparative* index, not an individual-prognosis tool -- the
paper's own stated purpose is "a useful tool for comparing living donor
kidneys to each other and to deceased donor kidneys," and that framing
should carry through to anything built on top of this module.

Known, load-bearing limitations -- not implementation details, clinical
ones:

- External discrimination is near-chance: C-statistic 0.55 in both the
  European validation (Rehse et al., NDT 2019, n=416) and the Canadian
  validation (Shantier et al., CJKHD 2020, n=645), versus 0.59 in the US
  derivation cohort (Massie 2016, n=36,025, 95% CI 0.55-0.62). A Japanese
  cohort (Transplant Proc 2020, n=133) found no association at all with
  3-year graft survival.
- Never validated in any South Asian population. The only race term is
  binary African-American vs. not -- this app's NIC-registered donors score
  +0 on that term regardless, an untested extrapolation, not a validated
  "not African-American" category. Same posture as RACE_FOR_SCORING in
  donor_risk_model.py.
- The eGFR term uses CKD-EPI (performs unevenly across ancestries) and the
  BMI term (+1.17/unit) was calibrated on US body habitus, where South Asian
  metabolic risk begins at a lower BMI.
- Two obsolete variants circulate with different coefficients and no SBP or
  weight-ratio terms: an ATC 2015 conference abstract and a 2017 KDIGO slide
  deck. If a source disagrees with COEFFICIENTS below, it is very likely one
  of those, not this paper.

See app/services/lkdpi_service.py for how this reference data is used, and
for the missing-input refusal contract (mirrors donor_risk_service.py's
"never substitute a default" rule).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LKDPICoefficients:
    """Field names mirror the paper's own formula (Massie 2016, full text)
    so the linear combination in lkdpi_service.py can be checked term-by-term
    against the source rather than a more "Pythonic" rewording."""

    intercept: float = -11.30
    donor_age_over_50_per_year: float = 1.85
    donor_egfr: float = -0.381
    donor_bmi: float = 1.17
    donor_african_american: float = 22.34
    donor_ever_smoked: float = 14.33
    donor_systolic_bp: float = 0.44
    both_male: float = -21.68
    abo_incompatible: float = 27.30
    biologically_unrelated: float = -10.61
    hla_b_mismatch: float = 8.57
    hla_dr_mismatch: float = 8.26
    weight_ratio_capped: float = -50.87


COEFFICIENTS = LKDPICoefficients()

# The donor/recipient weight ratio term is capped at 0.9 in the paper's own
# formula -- ratios above 0.9 (donor at or heavier than the recipient)
# contribute the same fixed benefit rather than an unbounded one.
WEIGHT_RATIO_CAP = 0.9

# There is no published band scheme for LKDPI -- Massie 2016 reports a
# median of 12.8 (IQR -0.8 to 27.2) in the US derivation cohort but does not
# define risk bands. These four are a project convention, anchored to that
# published distribution, NOT clinical policy -- see docs/clinical-basis.md.
# If the doctors this app serves want different boundaries, theirs win.
LKDPI_BAND_EXCELLENT = "excellent"
LKDPI_BAND_GOOD = "good"
LKDPI_BAND_MODERATE = "moderate"
LKDPI_BAND_MARGINAL = "marginal"


@dataclass(frozen=True)
class LKDPIBand:
    name: str
    label: str
    upper_bound: float | None  # exclusive; None = no upper bound


# Checked top-down, first match wins (see lkdpi_service.py). upper_bound is
# exclusive so a score of exactly 0 or exactly 20 falls into the band above
# it, not below.
LKDPI_BANDS: list[LKDPIBand] = [
    LKDPIBand(LKDPI_BAND_EXCELLENT, "Excellent", upper_bound=0),
    LKDPIBand(LKDPI_BAND_GOOD, "Good", upper_bound=20),
    LKDPIBand(LKDPI_BAND_MODERATE, "Moderate", upper_bound=40),
    LKDPIBand(LKDPI_BAND_MARGINAL, "Marginal", upper_bound=None),
]

# Range-warning ceilings/floors (D3 point 4) -- not clamped, only flagged.
# These are sanity bounds on plausible living-donor values, not taken from
# the paper's own derivation-cohort range (which it doesn't publish).
EGFR_RANGE = (15.0, 120.0)
BMI_RANGE = (18.0, 45.0)
SYSTOLIC_BP_RANGE = (90.0, 180.0)
DONOR_AGE_RANGE = (18, 85)
WEIGHT_RATIO_RANGE = (0.5, 1.5)

# Mirrors RACE_FOR_SCORING's donor_risk_model.py posture: the model has no
# coefficient for "other" so it scores identically to "not African-American"
# (+0) -- an extrapolation, not a third validated category.
POPULATION_VALIDATED_RACES = {"black", "white"}

SOURCE_CITATION = (
    "Massie ME, Leanza J, Fahmy LM, et al. A Risk Index for Living Donor "
    "Kidney Transplantation. Am J Transplant 2016;16(7):2077-2084. "
    "DOI: 10.1111/ajt.13709."
)

MODEL_LIMITATION_NOTE = (
    "External C-statistic 0.55 in both European and Canadian validation "
    "cohorts (near-chance discrimination); never validated in any South "
    "Asian population. Intended for comparing candidate donors to each "
    "other, not for individual prognosis. An aid to clinical assessment, "
    "not a substitute for clinical judgement."
)

POPULATION_EXTRAPOLATION_DISCLAIMER = (
    "The published model's only race term is African-American vs. not, so "
    "this donor's recorded race scores as 'not African-American' by "
    "default -- an extrapolation beyond the model's validated population, "
    "not a confirmed third category."
)


@dataclass(frozen=True)
class LKDPIReferenceCase:
    """Median US living donor from Massie 2016's derivation cohort --
    used ONLY as the baseline the single-factor override (below) measures
    deviation against. This is emphatically NOT a default: lkdpi_service.
    _missing_fields must never fall back to it, and no term computation may
    read it for an actual score. Its only consumer is the override check,
    which needs *some* fixed point of comparison to ask "how far from
    typical is this one factor," as opposed to "how big is this factor in
    absolute terms" -- the latter flags every continuous term on nearly
    every real donor (found 2026-08-10: an otherwise-ideal donor, age 35,
    eGFR 100, BMI 23, SBP 118, never-smoker, related, 0/0 mismatches,
    weight ratio 0.86, scored an excellent -14.17 and still tripped the
    override on 3 separate terms under the old absolute-magnitude check).
    Values chosen to make every binary/categorical term's reference
    contribution exactly 0 (not African-American, never smoked, not both
    male, ABO compatible, biologically related) -- see lkdpi_service.py's
    delta computation."""

    donor_age_years: int = 45
    donor_egfr: float = 95.0
    donor_bmi: float = 26.0
    donor_systolic_bp: float = 120.0
    weight_ratio: float = 0.9
    hla_b_mismatches: int = 1
    hla_dr_mismatches: int = 1
    donor_african_american: bool = False
    donor_ever_smoked: bool = False
    both_male: bool = False
    abo_incompatible: bool = False
    biologically_unrelated: bool = False


REFERENCE_CASE = LKDPIReferenceCase()

# NEWS2-style single-factor override (D5): any one component whose
# contribution DEVIATES from REFERENCE_CASE's by more than this many points
# gets its own callout regardless of the total. Deliberately a deviation
# check, not an absolute-magnitude check -- see LKDPIReferenceCase's
# docstring for why the original 25.0-on-raw-points version fired on nearly
# every donor. 15.0 is a project convention (docs/clinical-basis.md), not a
# clinically-derived cutoff.
SINGLE_FACTOR_OVERRIDE_THRESHOLD = 15.0

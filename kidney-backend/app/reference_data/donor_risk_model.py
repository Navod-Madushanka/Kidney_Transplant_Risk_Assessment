# app/reference_data/donor_risk_model.py
"""
Grams et al. 2016 living-kidney-donor-candidate kidney-failure risk
projection model. The source paper and its coefficients use "ESRD"
(end-stage renal disease); this module's own prose uses "kidney failure" /
"ESKD" (end-stage kidney disease) per the KDIGO 2020 consensus nomenclature
that retired "renal"/"ESRD" -- terminology only, the clinical model and its
coefficients are unchanged.

Source: Grams ME, Sang Y, Levey AS, et al. "Kidney-Failure Risk Projection
for the Living Kidney-Donor Candidate." N Engl J Med 2016;374:411-421.
DOI: 10.1056/NEJMoa1510491. Every coefficient, spline definition, and
base-case risk value below is transcribed verbatim from the paper's
Supplementary Appendix (freely available; "PDF last updated December 15,
2016"), Sections 3-4 -- not reconstructed from memory or a secondary
source. If these numbers are ever revisited, re-derive them from that
appendix directly rather than trust this file or any other relay of it.

This is a *projection*, not a diagnosis: it estimates the long-term
incidence of kidney failure a candidate would face if they did NOT donate,
based on their demographic and health profile. It says nothing about surgical risk
or the risk actually attributable to donating a kidney. See
app/services/donor_risk_service.py for how this reference data is used and
for the two-question split (quantitative projection vs. absolute
contraindication screen) the appendix itself draws.

Known, load-bearing limitation -- not an implementation detail, an ethical
one: the model was derived and validated entirely on US cohorts, stratified
Black or White. It has no coefficients for any other race category and no
non-US validation at all. This app's donors are NIC-registered, not a
population the model was ever tested against, regardless of which race is
recorded. RACE_FOR_SCORING documents how "other" is handled (scored against
the White row as the best available stand-in, not a validated category) --
see donor_risk_service.py for how that gets surfaced to the user rather than
quietly absorbed into a single number.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DonorRiskCoefficients:
    """The meta-analyzed beta coefficients (appendix Table 2, reproduced in
    the worked formula at appendix Sections 3-4). Field names mirror the
    paper's own variable names (eGFR1-4, BMI1-2) rather than a more
    "Pythonic" rewording, so the linear-predictor formula in
    donor_risk_service.py can be checked term-by-term against the source."""

    egfr1: float = 1.8879
    egfr2: float = 0.4884
    egfr3: float = 0.0203
    egfr4: float = -0.2420
    sbp_per_20mmhg: float = 0.3500
    antihypertensive_medication: float = 0.3012
    bmi1: float = -0.0241
    bmi2: float = 0.1474
    diabetes: float = 1.1008
    log10_acr: float = 1.0772
    former_smoker: float = 0.3700
    current_smoker: float = 0.5680


COEFFICIENTS = DonorRiskCoefficients()

# Base-case reference values the linear predictor is centered on (appendix
# Section 4 Step 1) -- fixed for every age/race/sex. Base-case eGFR instead
# varies by age band; see AGE_BANDS below.
BASE_CASE_SBP = 120.0
BASE_CASE_ACR = 4.0
BASE_CASE_BMI = 26.0

# eGFR spline knots (appendix Section 4 Step 2).
EGFR_KNOT_LOW = 60.0
EGFR_KNOT_MID = 90.0
EGFR_KNOT_HIGH = 120.0


@dataclass(frozen=True)
class AgeBand:
    label: str
    min_age: int
    max_age: int
    base_case_egfr: float


# Appendix Section 4 Step 1. Band widths are NOT uniform (15-25 spans 11
# years; the rest span 9) so this is transcribed as an explicit table, never
# derived arithmetically from a decade width. Ages outside 15-84 have no row
# here and no HX_TABLE row below -- the model defines no base case for them,
# so donor_risk_service.py must treat that as "cannot project", never
# clamp/extrapolate to the nearest band.
AGE_BANDS: list[AgeBand] = [
    AgeBand("15-25", 15, 25, 114.0),
    AgeBand("26-34", 26, 34, 106.0),
    AgeBand("35-44", 35, 44, 98.0),
    AgeBand("45-54", 45, 54, 90.0),
    AgeBand("55-64", 55, 64, 82.0),
    AgeBand("65-74", 65, 74, 74.0),
    AgeBand("75-84", 75, 84, 66.0),
]


@dataclass(frozen=True)
class HxEntry:
    age_band_label: str
    race: str  # "black" | "white" -- the model's own two validated categories
    sex: str  # "male" | "female"
    fifteen_year_percent: float
    lifetime_percent: float


# Appendix Section 4 Step 4, Tables A (15-year) and B (lifetime): the
# model's own published base-case absolute risk (Hx), by age band x race x
# sex. This is fixed published data, not something this app calculates.
# Point estimates only -- the appendix also publishes a 95% CI alongside
# each of these, not carried here since donor_risk_service.py reports a
# point estimate, not an interval.
HX_TABLE: list[HxEntry] = [
    HxEntry("15-25", "black", "male", 0.08, 1.62),
    HxEntry("15-25", "black", "female", 0.05, 1.23),
    HxEntry("15-25", "white", "male", 0.02, 0.58),
    HxEntry("15-25", "white", "female", 0.01, 0.35),
    HxEntry("26-34", "black", "male", 0.16, 1.33),
    HxEntry("26-34", "black", "female", 0.09, 1.03),
    HxEntry("26-34", "white", "male", 0.04, 0.53),
    HxEntry("26-34", "white", "female", 0.03, 0.38),
    HxEntry("35-44", "black", "male", 0.24, 1.00),
    HxEntry("35-44", "black", "female", 0.15, 0.85),
    HxEntry("35-44", "white", "male", 0.06, 0.43),
    HxEntry("35-44", "white", "female", 0.04, 0.29),
    HxEntry("45-54", "black", "male", 0.27, 0.66),
    HxEntry("45-54", "black", "female", 0.16, 0.50),
    HxEntry("45-54", "white", "male", 0.08, 0.31),
    HxEntry("45-54", "white", "female", 0.06, 0.21),
    HxEntry("55-64", "black", "male", 0.32, 0.49),
    HxEntry("55-64", "black", "female", 0.18, 0.31),
    HxEntry("55-64", "white", "male", 0.13, 0.26),
    HxEntry("55-64", "white", "female", 0.08, 0.15),
    HxEntry("65-74", "black", "male", 0.14, 0.17),
    HxEntry("65-74", "black", "female", 0.19, 0.22),
    HxEntry("65-74", "white", "male", 0.12, 0.15),
    HxEntry("65-74", "white", "female", 0.07, 0.08),
    HxEntry("75-84", "black", "male", 0.12, 0.12),
    HxEntry("75-84", "black", "female", 0.06, 0.06),
    HxEntry("75-84", "white", "male", 0.05, 0.06),
    HxEntry("75-84", "white", "female", 0.03, 0.03),
]

# "other" is not a validated third category -- see module docstring and
# app/models/enums.py's Race docstring. Scored against "white" as the best
# available stand-in so every donor still gets a number;
# donor_risk_service.py sets population_validated=False whenever this
# mapping is actually invoked, and the frontend turns that into a permanent,
# non-dismissible banner rather than a footnote.
RACE_FOR_SCORING = {
    "black": "black",
    "white": "white",
    "other": "white",
}

# Appendix Section 3 Step 1 -- absolute contraindications used to build the
# model's own "low-risk" reference population. This app can only check the
# three with a corresponding Donor field (eGFR, blood pressure, urine ACR).
# Insulin-dependent diabetes, a *count* of antihypertensive medications, and
# history of coronary heart disease/stroke/CHF/peripheral arterial disease
# all need data this app doesn't capture -- donor_risk_service.py lists
# those explicitly as CONTRAINDICATION_CRITERIA_NOT_ASSESSED rather than
# silently omitting them.
CONTRAINDICATION_EGFR_FLOOR = 45.0
CONTRAINDICATION_ACR_CEILING = 300.0
CONTRAINDICATION_SBP_WITH_MEDICATION = 160
CONTRAINDICATION_DBP_WITH_MEDICATION = 90
CONTRAINDICATION_SBP_WITHOUT_MEDICATION = 170
CONTRAINDICATION_DBP_WITHOUT_MEDICATION = 100

SOURCE_CITATION = (
    "Grams ME, Sang Y, Levey AS, et al. Kidney-Failure Risk Projection for "
    "the Living Kidney-Donor Candidate. N Engl J Med 2016;374:411-421. "
    "DOI: 10.1056/NEJMoa1510491."
)

GENERAL_POPULATION_DISCLAIMER = (
    "This model was derived and validated entirely on US cohorts and has no "
    "non-US validation. Treat these figures as an illustrative estimate, "
    "not a clinically validated risk for this patient."
)

OTHER_RACE_EXTRAPOLATION_DISCLAIMER = (
    "The published model has coefficients for Black and White candidates "
    "only. This donor's recorded race is neither, so this projection was "
    "scored using the White coefficients as the closest available stand-in "
    "-- an extrapolation beyond the model's validated population, not a "
    "third validated category."
)

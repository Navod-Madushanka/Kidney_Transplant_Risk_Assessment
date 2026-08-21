# app/services/compatibility_precondition_service.py
"""
Shared "is this pairing ready to check" logic, used by two endpoints that
share their source of truth (unverified_data_gaps, compute_hla_mismatch_result)
but read it at different strictness:

- POST /compatibility/check (app/api/compatibility.py) -- hard-blocks on
  ANY unverified OCR data before running the pipeline at all (every gap in
  _UNVERIFIED_CHECKS, unfiltered -- see unverified_data_reasons), AND on
  incomplete A/B/DRB1 HLA typing (compute_hla_mismatch_result's
  data_completeness). The latter is enforced directly by the endpoint
  itself, not only by the readiness preview below -- a caller that reaches
  POST /compatibility/check by any route other than the wizard (Swagger,
  a script, a future client) gets the same 422 a wizard user would have
  been stopped by earlier, rather than a report built on worst-cased,
  invented mismatch data. See app/api/compatibility.py's precondition
  block.
- GET /compatibility/readiness (this module's build_compatibility_readiness)
  -- a preview a doctor can look at BEFORE submitting, naming exactly what's
  missing rather than making them find out via a failed submission. Its
  `blocking` list deliberately EXCLUDES a subset of unverified_data_gaps
  (see _READINESS_NON_BLOCKING_CODES) -- gaps the wizard has its own later
  step dedicated to resolving, where blocking Continue here would only
  dead-end the doctor before they ever reach it. The wizard's submission
  flow persists that step's confirmation before POST /compatibility/check
  ever runs, so the hard block above is still satisfied for a doctor who
  actually completes the wizard; it only fires for real when something
  didn't get confirmed.

Extracted 2026-08-10 (Part E) after the wizard stopped creating a fresh
patient/donor on every check and started running checks against existing,
possibly-incomplete records -- see the module docstring on
app/services/lkdpi_service.py for why an incomplete record used to be
impossible (every check got a brand-new, identically-blank pair) and isn't
anymore.

Three categories of "not ready," never conflated:

1. `blocking` -- POST /compatibility/check refuses to run at all: either
   unverified OCR data the wizard has no later step to re-confirm, or
   incomplete A/B/DRB1 HLA typing (see compute_hla_mismatch_result --
   Step 3 would otherwise worst-case the missing locus/loci rather than
   ever refuse to run). Continue should be disabled.
2. Unverified-but-wizard-resolvable (_READINESS_NON_BLOCKING_CODES) --
   POST /compatibility/check would still hard-block on these too, but the
   readiness preview doesn't, because the wizard already has a dedicated
   step that re-confirms this exact data before submission.
3. Score gaps (`lkdpi_gaps`, `donor_risk_projection_gaps`,
   `donor_risk_contraindication_gaps`) -- the check itself runs fine; a
   downstream score is withheld. Informational only, Continue stays
   enabled. Missing LKDPI inputs are deliberately NOT blocking: a doctor
   with no eGFR result yet must still be able to run ABO / HLA / DSA /
   crossmatch (see docs/clinical-basis.md and lkdpi_service.py's own
   missing-data contract).
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.patient import Patient
from app.services.abo_service import check_abo_compatibility
from app.services.donor_risk_input_adapter import donor_risk_input_from_record
from app.services.donor_risk_service import assess_donor_risk
from app.services.hla_mismatch_service import (
    MISMATCH_COUNTED_LOCI,
    MismatchResult,
    calculate_mismatch_result,
)
from app.services.hla_typing_service import (
    build_partial_typing_dict,
    get_donor_hla_typing_entries,
    get_patient_hla_typing_entries,
)
from app.services.lkdpi_input_adapter import lkdpi_input_from_records
from app.services.lkdpi_service import calculate_lkdpi

# donor_risk_service.py returns raw Donor field names in its missing-*
# lists (e.g. "egfr", "is_on_antihypertensive_medication") -- fine for a
# developer, not for a doctor reading a readiness panel. Mirrors
# DonorSafetyAssessmentPage.jsx's FIELD_LABELS exactly; only the fields
# donor_risk_service.py can actually report as missing need an entry.
DONOR_RISK_FIELD_LABELS: dict[str, str] = {
    "age_years": "donor age",
    "sex": "donor sex",
    "race": "donor race",
    "egfr": "donor eGFR",
    "systolic_bp": "donor systolic BP",
    "diastolic_bp": "donor diastolic BP",
    "is_on_antihypertensive_medication": "donor antihypertensive medication use",
    "bmi": "donor BMI",
    "has_diabetes": "donor diabetes status",
    "urine_acr": "donor urine ACR",
    "smoking_status": "donor smoking status",
}


@dataclass(frozen=True)
class ReadinessGap:
    code: str
    label: str
    subject: str  # "patient" | "donor"


@dataclass
class CompatibilityReadiness:
    can_run: bool
    blocking: list[ReadinessGap] = field(default_factory=list)
    lkdpi_gaps: list[ReadinessGap] = field(default_factory=list)
    donor_risk_projection_gaps: list[ReadinessGap] = field(default_factory=list)
    donor_risk_contraindication_gaps: list[ReadinessGap] = field(default_factory=list)


# (code, label, subject, attribute-name-on-Patient/Donor). label text is
# written to read naturally when joined with ", " into the 422 message
# POST /compatibility/check raises -- see unverified_data_reasons below,
# which is the ONE place both that message and the readiness panel read
# their wording from.
_UNVERIFIED_CHECKS: tuple[tuple[str, str, str, str], ...] = (
    (
        "patient_details_unverified",
        "the patient's demographic details (name/DOB/blood type)",
        "patient",
        "details_verified",
    ),
    (
        "donor_details_unverified",
        "the donor's demographic details (name/DOB/blood type)",
        "donor",
        "details_verified",
    ),
    (
        "patient_hla_typing_unverified",
        "the patient's HLA typing",
        "patient",
        "hla_typing_verified",
    ),
    (
        "donor_hla_typing_unverified",
        "the donor's HLA typing",
        "donor",
        "hla_typing_verified",
    ),
    (
        "patient_antibody_profile_unverified",
        "the patient's antibody/bead-specificity profile",
        "patient",
        "antibody_profile_verified",
    ),
)


def unverified_data_gaps(patient: Patient, donor: Donor) -> list[ReadinessGap]:
    """The single source of truth for "does this pairing have unconfirmed
    OCR data on it" -- both POST /compatibility/check's hard block and
    GET /compatibility/readiness's blocking list read from this, so they
    can't independently drift on what counts."""
    gaps = []
    for code, label, subject, attr in _UNVERIFIED_CHECKS:
        record = patient if subject == "patient" else donor
        if not getattr(record, attr):
            gaps.append(ReadinessGap(code=code, label=label, subject=subject))
    return gaps


# Excluded from the READINESS PREVIEW's blocking list only -- POST
# /compatibility/check's hard block (unverified_data_reasons, unfiltered)
# still refuses to run against this regardless. BeadSpecificityStep.jsx
# re-confirms bead/antibody data as its own dedicated wizard step
# regardless of whether THIS session is what extracted it (it reads
# patientRecord.antibody_profile_verified directly, same as this flag) --
# so blocking Continue here, before the doctor ever reaches that step,
# would dead-end them into an unnecessary detour to the patient's profile
# page for something the wizard already asks them to review a few steps
# later. Same reasoning NewPairPage/handleRegister already applies when
# registering a brand-new pair (see this module's own docstring: "Showing
# 'these must be resolved' for a gap the very next steps exist to fill
# would just dead-end the doctor"). Safe to exclude here because the
# wizard's submission flow (compatibilityWizard.js) persists
# BeadSpecificityStep's confirmation via replacePatientAntibodyProfiles
# BEFORE POST /compatibility/check ever runs -- a doctor who actually
# completes the wizard satisfies the hard check naturally; it only fires
# as a genuine last-resort safety net (e.g. a check submitted without
# going through the wizard's own confirmation step).
_READINESS_NON_BLOCKING_CODES = frozenset({"patient_antibody_profile_unverified"})


def unverified_data_reasons(patient: Patient, donor: Donor) -> list[str]:
    """Sentence-fragment list for POST /compatibility/check's 422 detail
    message -- derived from unverified_data_gaps' labels, not a second
    hand-written list, so the two can't say different things."""
    return [gap.label for gap in unverified_data_gaps(patient, donor)]


async def compute_hla_mismatch_result(
    db: AsyncSession, patient: Patient, donor: Donor
) -> MismatchResult:
    """The single source of truth for "is this pairing's A/B/DRB1 HLA
    typing complete enough to trust a mismatch count" -- both POST
    /compatibility/check's hard block (see its module-level docstring's
    category 1) and GET /compatibility/readiness's blocking list call this,
    so they can't independently drift on what counts as complete. Mirrors
    exactly what Step 3 of the pipeline itself does (hla_mismatch_service.py
    via match_pipeline.py) -- same queries, same partial-typing-dict
    shaping -- so a "complete" verdict here is never contradicted once the
    pipeline actually runs.
    """
    patient_hla_entries = await get_patient_hla_typing_entries(db, patient.id)
    donor_hla_entries = await get_donor_hla_typing_entries(db, donor.id)
    patient_typing = build_partial_typing_dict(patient_hla_entries, MISMATCH_COUNTED_LOCI)
    donor_typing = build_partial_typing_dict(donor_hla_entries, MISMATCH_COUNTED_LOCI)
    return calculate_mismatch_result(patient_typing, donor_typing)


async def build_compatibility_readiness(
    db: AsyncSession, patient: Patient, donor: Donor
) -> CompatibilityReadiness:
    blocking: list[ReadinessGap] = [
        gap
        for gap in unverified_data_gaps(patient, donor)
        if gap.code not in _READINESS_NON_BLOCKING_CODES
    ]

    mismatch_result = await compute_hla_mismatch_result(db, patient, donor)

    for missing in mismatch_result.missing_inputs:
        subject = "patient" if missing.startswith("patient") else "donor"
        blocking.append(
            ReadinessGap(
                code=f"missing_hla_{missing.replace(' ', '_')}",
                label=missing,
                subject=subject,
            )
        )

    # A real (non-persisted, non-audited) ABO check purely to feed LKDPI's
    # abo_incompatible input -- same pure function Step 1 of the pipeline
    # itself calls. Cheap and side-effect-free; not a substitute for the
    # actual pipeline run.
    abo_result = check_abo_compatibility(patient.blood_type.value, donor.blood_type.value)
    lkdpi_result = calculate_lkdpi(
        lkdpi_input_from_records(
            donor, patient, mismatch_result, abo_incompatible=not abo_result.is_compatible
        )
    )
    lkdpi_gaps = [
        ReadinessGap(
            code=f"lkdpi_{field_name.replace(' ', '_')}",
            label=field_name,
            subject="patient" if field_name.startswith("recipient") else "donor",
        )
        for field_name in lkdpi_result.missing_inputs
    ]

    donor_risk_result = assess_donor_risk(donor_risk_input_from_record(donor))
    donor_risk_projection_gaps = [
        ReadinessGap(
            code=f"donor_risk_projection_{field_name}",
            label=DONOR_RISK_FIELD_LABELS.get(field_name, field_name),
            subject="donor",
        )
        for field_name in donor_risk_result.missing_projection_predictors
    ]
    donor_risk_contraindication_gaps = [
        ReadinessGap(
            code=f"donor_risk_contraindication_{field_name}",
            label=DONOR_RISK_FIELD_LABELS.get(field_name, field_name),
            subject="donor",
        )
        for field_name in donor_risk_result.missing_contraindication_predictors
    ]

    return CompatibilityReadiness(
        can_run=len(blocking) == 0,
        blocking=blocking,
        lkdpi_gaps=lkdpi_gaps,
        donor_risk_projection_gaps=donor_risk_projection_gaps,
        donor_risk_contraindication_gaps=donor_risk_contraindication_gaps,
    )

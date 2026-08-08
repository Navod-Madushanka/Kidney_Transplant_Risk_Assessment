# app/services/match_pipeline.py
"""
The sequential compatibility pipeline (see the project roadmap, Phase 3 —
"Clinical Pipeline Redesign", added 2026-07-30 from direct doctor feedback).

Each step below either halts the check with a specific overall_status, or
proceeds to the next step. As of this pass:

  1. ABO             - real gate (unchanged from before this pass)
  2. Sensitization   - NOT YET a gate. Computed and stored for reference,
                        but doesn't halt anything. The doctors asked for
                        this to become its own reject/proceed step, but
                        didn't specify the accept/reject rule yet (see the
                        roadmap's Phase 3 open questions) — left alone
                        rather than guessing a clinical threshold.
  3. Mismatches      - real gate (NEW this pass). A/B/DRB1 only, wired from
                        app/reference_data/mismatch_buckets.py.
  4. PRA             - NOT a gate (changed back this pass — see below).
                        Wired from app/reference_data/pra_buckets.py.
                        Computed and bucketed for every check, but never
                        halts, same as Step 2.
  5. DSA             - real gate (CHANGED this pass). Flat MFI 1000 cutoff
                        from app/reference_data/dsa_threshold.py, no longer
                        adjusted by the Sensitization score.
  6. Crossmatch      - real gate (NEW this pass). Submitted with the check
                        request rather than looked up, since it's a same-
                        day result tied to this specific pairing. If not
                        submitted at all, the pipeline stops at
                        "pending_crossmatch" rather than silently treating
                        a missing crossmatch as a pass.
  7. Final risk level - NEW this pass. Combines the Step 3 and Step 4
                        buckets via risk_classification.py. Only computed
                        when both bucket inputs are known (Step 4's bucket
                        can be None if risk_classification.py has no
                        doctor-specified point value for its bucket yet —
                        currently just ">60%", see below) AND Step 3's mismatch count
                        was computed from complete A/B/DRB1 typing on both
                        sides (see MismatchResult.data_completeness in
                        hla_mismatch_service.py) — in any of these cases
                        final_risk_level stays None rather than guessing or
                        presenting a risk level built on absent data.

Step 4 (PRA) briefly halted the pipeline outright above
MAX_ACCEPTABLE_PRA_PERCENT (60%) — reverted 2026-08-08 as a clinical
category error. cPRA measures how hard a patient is to match against the
*population*; it says nothing about this specific donor. Rejecting a
pairing on cPRA meant the more sensitised a patient was, the more certainly
the system refused the one compatible donor they'd actually found — exactly
backwards, since Steps 5 (DSA) and 6 (crossmatch) already test this
specific pairing directly and are what should decide accept/reject on
sensitisation-related risk. PRA is bucketed and returned for every check
(clinical context, and it still feeds Step 7 when a doctor-specified point
value exists for its bucket — see risk_classification.py), but never halts
Step 3+ on its own, same as Step 2.

The old continuous HLA scoring (hla_scoring_service.py, all 9 loci) and its
4-tier risk_tier are kept and still computed on a full "completed" run, for
reference/comparison during the transition — they are no longer part of the
gate sequence itself. Because Step 3 only requires A/B/DRB1 (not all 9
loci), it's now possible to reach "completed" without a full enough panel
for the legacy score; that computation is wrapped defensively so an
incomplete panel degrades to hla_scoring_result=None instead of a 500.
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.patient import Patient
from app.reference_data.dsa_threshold import DSA_MFI_THRESHOLD
from app.reference_data.hla_antigen_frequencies import (
    HLA_ANTIGEN_FREQUENCIES,
    HLA_FREQUENCY_TABLE_CITATION,
    HLA_FREQUENCY_TABLE_SAMPLE_SIZE,
    HLA_FREQUENCY_TABLE_VERSION,
)
from app.reference_data.risk_classification import classify_risk
from app.services.abo_service import ABOResult, check_abo_compatibility
from app.services.antibody_profile_service import (
    get_patient_antibody_profiles,
    get_patient_sensitized_antigens,
)
from app.services.cpra_service import CPRAResult, calculate_cpra
from app.services.crossmatch_service import CrossmatchResult, check_crossmatch
from app.services.dsa_service import DEFAULT_MFI_CUTOFF, DSAResult, PatientAntibody, check_dsa
from app.services.hla_mismatch_service import (
    MISMATCH_COUNTED_LOCI,
    MismatchResult,
    calculate_mismatch_result,
)
from app.services.hla_scoring_service import HLAScoringResult, calculate_hla_risk_score
from app.services.hla_typing_service import (
    build_partial_typing_dict,
    get_donor_hla_typing_dict,
    get_donor_hla_typing_entries,
    get_patient_hla_typing_dict,
    get_patient_hla_typing_entries,
    hla_antigen_designation,
    normalize_antibody_antigen,
)
from app.services.pra_bucket_service import PRABucketResult, calculate_pra_bucket
from app.services.risk_tier_service import get_risk_tier
from app.services.sensitization_event_service import get_patient_sensitization_event_types
from app.services.sensitization_service import SensitizationResult, calculate_sensitization_score


@dataclass
class CrossmatchInputData:
    """Plain-data mirror of schemas.match_report.CrossmatchInput — kept
    separate from the Pydantic schema so this service layer doesn't import
    from schemas/ (services are lower in the dependency stack than the API
    layer everywhere else in this codebase)."""

    is_positive: bool
    t_cell_result: Optional[str] = None
    b_cell_result: Optional[str] = None
    remarks: Optional[str] = None


@dataclass
class MatchPipelineResult:
    overall_status: str
    abo_result: ABOResult
    sensitization_result: Optional[SensitizationResult] = None
    mismatch_result: Optional[MismatchResult] = None
    pra_bucket_result: Optional[PRABucketResult] = None
    dsa_result: Optional[DSAResult] = None
    crossmatch_result: Optional[CrossmatchResult] = None
    hla_scoring_result: Optional[HLAScoringResult] = None
    risk_tier: Optional[str] = None
    cpra_result: Optional[CPRAResult] = None
    final_risk_level: Optional[str] = None


async def run_match_pipeline(
    db: AsyncSession,
    patient: Patient,
    donor: Donor,
    crossmatch_input: Optional[CrossmatchInputData] = None,
) -> MatchPipelineResult:
    # --- Step 1: ABO ---------------------------------------------------
    abo_result = check_abo_compatibility(
        patient.blood_type.value, donor.blood_type.value
    )

    if not abo_result.is_compatible:
        return MatchPipelineResult(
            overall_status="halted_abo_fail",
            abo_result=abo_result,
        )

    # --- Step 2: Sensitization (informational only — see module docstring) ---
    event_types = await get_patient_sensitization_event_types(db, patient.id)
    sensitization_result = calculate_sensitization_score(
        event_types=event_types, base_mfi_cutoff=DEFAULT_MFI_CUTOFF
    )

    # --- Step 3: HLA mismatches (A/B/DRB1 only) -------------------------
    patient_hla_entries = await get_patient_hla_typing_entries(db, patient.id)
    donor_hla_entries_all = await get_donor_hla_typing_entries(db, donor.id)
    patient_mismatch_typing = build_partial_typing_dict(patient_hla_entries, MISMATCH_COUNTED_LOCI)
    donor_mismatch_typing = build_partial_typing_dict(donor_hla_entries_all, MISMATCH_COUNTED_LOCI)
    mismatch_result = calculate_mismatch_result(patient_mismatch_typing, donor_mismatch_typing)

    if mismatch_result.is_halted:
        return MatchPipelineResult(
            overall_status="halted_mismatch_reject",
            abo_result=abo_result,
            sensitization_result=sensitization_result,
            mismatch_result=mismatch_result,
        )

    # --- Step 4: PRA -----------------------------------------------------
    # Uses the existing cPRA sensitized-antigen threshold (DEFAULT_MFI_CUTOFF,
    # a fixed 2000 from dsa_service.py) — this is a different cutoff from the
    # Step 5 DSA gate below and doctors didn't ask to change it.
    # Normalized the same way Step 5 normalizes patient_antibodies below (a
    # raw chart antigen like "B45,Bw6" must have its Bw4/Bw6 suffix stripped
    # to match a plain "B45" reference-table key).
    sensitized_antigens = [
        normalize_antibody_antigen(antigen)
        for antigen in await get_patient_sensitized_antigens(
            db, patient.id, DEFAULT_MFI_CUTOFF
        )
    ]
    cpra_result = calculate_cpra(
        sensitized_antigens=sensitized_antigens,
        antigen_frequencies=HLA_ANTIGEN_FREQUENCIES,
        reference_sample_size=HLA_FREQUENCY_TABLE_SAMPLE_SIZE,
        reference_table_version=HLA_FREQUENCY_TABLE_VERSION,
        source_citation=HLA_FREQUENCY_TABLE_CITATION,
    )
    pra_bucket_result = calculate_pra_bucket(cpra_result)
    # Informational only — see the module docstring's note on Step 4. cPRA
    # is population-level, not pair-specific, so it never halts the
    # pipeline; Steps 5/6 below are the real pair-specific gates.

    # --- Step 5: DSA -------------------------------------------------------
    # Flat threshold now (DSA_MFI_THRESHOLD = 1000), no longer adjusted by
    # the Sensitization score's adjusted_mfi_cutoff.
    antibody_rows = await get_patient_antibody_profiles(db, patient.id)
    patient_antibodies = [
        PatientAntibody(antigen=normalize_antibody_antigen(row.antigen), mfi=float(row.mfi))
        for row in antibody_rows
    ]
    donor_hla_antigens = [
        hla_antigen_designation(row.locus.value, allele)
        for row in donor_hla_entries_all
        for allele in (row.allele_1, row.allele_2)
    ]

    dsa_result = check_dsa(
        patient_antibodies=patient_antibodies,
        donor_hla_antigens=donor_hla_antigens,
        mfi_cutoff_value=DSA_MFI_THRESHOLD,
    )

    if dsa_result.is_halted:
        return MatchPipelineResult(
            overall_status="halted_dsa_trigger",
            abo_result=abo_result,
            sensitization_result=sensitization_result,
            mismatch_result=mismatch_result,
            pra_bucket_result=pra_bucket_result,
            cpra_result=cpra_result,
            dsa_result=dsa_result,
        )

    # --- Step 6: Crossmatch -------------------------------------------------
    if crossmatch_input is None:
        # Every gate through Step 5 passed, but Step 6/7 can't run without a
        # submitted crossmatch result. Distinct status so callers don't
        # mistake this for a final "completed" result.
        return MatchPipelineResult(
            overall_status="pending_crossmatch",
            abo_result=abo_result,
            sensitization_result=sensitization_result,
            mismatch_result=mismatch_result,
            pra_bucket_result=pra_bucket_result,
            cpra_result=cpra_result,
            dsa_result=dsa_result,
        )

    crossmatch_result = check_crossmatch(
        is_positive=crossmatch_input.is_positive,
        t_cell_result=crossmatch_input.t_cell_result,
        b_cell_result=crossmatch_input.b_cell_result,
        remarks=crossmatch_input.remarks,
    )

    if crossmatch_result.is_halted:
        return MatchPipelineResult(
            overall_status="halted_crossmatch_positive",
            abo_result=abo_result,
            sensitization_result=sensitization_result,
            mismatch_result=mismatch_result,
            pra_bucket_result=pra_bucket_result,
            cpra_result=cpra_result,
            dsa_result=dsa_result,
            crossmatch_result=crossmatch_result,
        )

    # --- Step 7: final risk classification ----------------------------------
    # Only possible once both bucket inputs are known and trustworthy.
    # pra_bucket_result's bucket may be None if there wasn't enough
    # population data for cPRA yet, and mismatch_result.data_completeness is
    # False if A/B/DRB1 typing was missing on either side (Step 3 then
    # scored the missing loci at their worst case rather than as a match) —
    # in either case we deliberately leave final_risk_level unset rather
    # than guessing or presenting a risk level built on absent data.
    final_risk_level = None
    if pra_bucket_result.bucket_name is not None and mismatch_result.data_completeness:
        final_risk_level = classify_risk(mismatch_result.bucket_name, pra_bucket_result.bucket_name)

    # --- Legacy continuous score (reference only, see module docstring) ----
    hla_scoring_result = None
    risk_tier = None
    try:
        donor_hla_typing = await get_donor_hla_typing_dict(db, donor.id)
        patient_hla_typing = await get_patient_hla_typing_dict(db, patient.id)
        hla_scoring_result = calculate_hla_risk_score(patient_hla_typing, donor_hla_typing)
        risk_tier = get_risk_tier(hla_scoring_result.total_score)
    except ValueError:
        # Legacy score needs a complete 9-locus panel; the new pipeline only
        # requires A/B/DRB1, so a real check can now reach "completed"
        # without qualifying for the legacy score too — that's fine, it's
        # reference-only, not required for a final result.
        pass

    return MatchPipelineResult(
        overall_status="completed",
        abo_result=abo_result,
        sensitization_result=sensitization_result,
        mismatch_result=mismatch_result,
        pra_bucket_result=pra_bucket_result,
        cpra_result=cpra_result,
        dsa_result=dsa_result,
        crossmatch_result=crossmatch_result,
        hla_scoring_result=hla_scoring_result,
        risk_tier=risk_tier,
        final_risk_level=final_risk_level,
    )

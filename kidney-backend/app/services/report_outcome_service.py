# app/services/report_outcome_service.py
"""
Builds the single headline ReportOutcome for a match report — see
app/reference_data/report_outcome.py for the verdict definitions and the
decision table this implements.

Takes plain dicts/values, not a Pydantic model or ORM object: services
don't import from app/schemas/ (see CrossmatchInputData's comment in
match_pipeline.py), and this needs to run identically from
run_match_pipeline (dataclasses, pre-persistence) and from the Alembic
migration that backfills existing rows (raw JSONB dicts, no app imports at
all — see that migration for why).
"""
from typing import Optional

from app.reference_data.report_outcome import (
    HALTED_STATUSES,
    HIGH_CPRA_BUCKET_NAME,
    REVIEW_FLAG_DSA_REQUIRES_REVIEW,
    REVIEW_FLAG_HIGH_CPRA,
    REVIEW_FLAG_INCOMPLETE_TYPING,
    REVIEW_FLAG_LABELS,
    REVIEW_FLAG_UNCLASSIFIED_RISK,
    TOTAL_STEPS,
    VERDICT_CANNOT_ASSESS,
    VERDICT_COMPATIBLE,
    VERDICT_LABELS,
    VERDICT_NOT_COMPATIBLE,
    VERDICT_PROCEED_CAUTION,
    ReportOutcome,
)

HALT_STEP_BY_STATUS: dict[str, int] = {
    "halted_abo_fail": 1,
    "halted_mismatch_reject": 3,
    "halted_dsa_trigger": 5,
    "halted_crossmatch_positive": 6,
}


def _halted_headline_and_detail(
    overall_status: str,
    abo_result: Optional[dict],
    mismatch_result: Optional[dict],
    dsa_result: Optional[dict],
    crossmatch_result: Optional[dict],
) -> tuple[str, str]:
    if overall_status == "halted_abo_fail":
        recipient_type = abo_result.get("recipient_type") if abo_result else "unknown"
        donor_type = abo_result.get("donor_type") if abo_result else "unknown"
        return (
            "ABO incompatible",
            f"Recipient blood type {recipient_type} is not compatible with donor type {donor_type}.",
        )

    if overall_status == "halted_mismatch_reject":
        total = mismatch_result.get("total_mismatches") if mismatch_result else "unknown"
        bucket = mismatch_result.get("bucket_name") if mismatch_result else "unknown"
        return (
            "Too many HLA mismatches",
            f"{total} HLA mismatches across A/B/DRB1 (bucket: {bucket}) — above the acceptable threshold.",
        )

    if overall_status == "halted_dsa_trigger":
        matches = (dsa_result or {}).get("matches") or []
        strong = [m for m in matches if m.get("severity") and m.get("severity") not in ("weak", "moderate")]
        target = strong[0] if strong else (matches[0] if matches else None)
        if target:
            return (
                "Donor-specific antibody detected",
                f"Strong DSA against donor HLA {target.get('antigen')} with an MFI of {target.get('mfi')}.",
            )
        return ("Donor-specific antibody detected", "A strong donor-specific antibody was detected.")

    if overall_status == "halted_crossmatch_positive":
        return (
            "Positive crossmatch",
            "The patient's serum reacted against donor cells on crossmatch — immunologically incompatible.",
        )

    return ("Not compatible", "This pairing did not clear a required gate.")


def build_report_outcome(
    overall_status: str,
    abo_result: Optional[dict] = None,
    mismatch_result: Optional[dict] = None,
    pra_bucket_result: Optional[dict] = None,
    dsa_result: Optional[dict] = None,
    crossmatch_result: Optional[dict] = None,
    final_risk_level: Optional[str] = None,
) -> ReportOutcome:
    """Each *_result argument is the plain dict shape already stored on
    MatchReport (i.e. what asdict() produces on the corresponding pipeline
    dataclass) — None for any step the pipeline didn't reach.
    """
    completed = overall_status == "completed"

    # --- Row 1: any halted_* status -------------------------------------
    if overall_status in HALTED_STATUSES:
        headline, detail = _halted_headline_and_detail(
            overall_status, abo_result, mismatch_result, dsa_result, crossmatch_result
        )
        return ReportOutcome(
            verdict=VERDICT_NOT_COMPATIBLE,
            verdict_label=VERDICT_LABELS[VERDICT_NOT_COMPATIBLE],
            headline=headline,
            detail=detail,
            risk_level=None,
            determined_at_step=HALT_STEP_BY_STATUS[overall_status],
            total_steps=TOTAL_STEPS,
            action_required=(
                "This donor cannot proceed. Add the patient to the paired exchange pool, "
                "or search for another donor."
            ),
            review_flags=[],
        )

    # --- Row 2: pending crossmatch ---------------------------------------
    if overall_status == "pending_crossmatch":
        return ReportOutcome(
            verdict=VERDICT_CANNOT_ASSESS,
            verdict_label=VERDICT_LABELS[VERDICT_CANNOT_ASSESS],
            headline="Awaiting crossmatch",
            detail=(
                "Every gate through Step 5 (ABO, mismatches, DSA) passed, but no crossmatch "
                "result was submitted with this check."
            ),
            risk_level=None,
            determined_at_step=6,
            total_steps=TOTAL_STEPS,
            action_required="Submit a crossmatch result and re-run the check.",
            review_flags=[],
        )

    if not completed:
        # Defensive only — overall_status is a closed set of six values
        # produced by run_match_pipeline; nothing else should reach here.
        return ReportOutcome(
            verdict=VERDICT_CANNOT_ASSESS,
            verdict_label=VERDICT_LABELS[VERDICT_CANNOT_ASSESS],
            headline="Unknown status",
            detail=f"Unrecognized overall_status '{overall_status}'.",
            risk_level=None,
            determined_at_step=0,
            total_steps=TOTAL_STEPS,
            action_required=None,
            review_flags=[],
        )

    # --- Row 3: completed but incomplete typing --------------------------
    data_completeness = (mismatch_result or {}).get("data_completeness", True)
    if data_completeness is False:
        missing_inputs = (mismatch_result or {}).get("missing_inputs") or []
        flag = {
            "code": REVIEW_FLAG_INCOMPLETE_TYPING,
            "label": REVIEW_FLAG_LABELS[REVIEW_FLAG_INCOMPLETE_TYPING],
            "detail": (
                f"Missing: {', '.join(missing_inputs)}." if missing_inputs else "HLA typing is incomplete."
            ),
        }
        if missing_inputs:
            action_required = f"Enter the {missing_inputs[0]}, then re-run the check."
        else:
            action_required = "Complete HLA typing, then re-run the check."
        return ReportOutcome(
            verdict=VERDICT_CANNOT_ASSESS,
            verdict_label=VERDICT_LABELS[VERDICT_CANNOT_ASSESS],
            headline="Incomplete HLA typing",
            detail=(
                f"{', '.join(missing_inputs)} missing — the mismatch count is a conservative "
                "worst-case estimate, not a confirmed result."
                if missing_inputs
                else "HLA typing is incomplete for one or more required loci."
            ),
            risk_level=None,
            determined_at_step=3,
            total_steps=TOTAL_STEPS,
            action_required=action_required,
            review_flags=[flag],
        )

    # --- Build review flags for rows 4/5/6 --------------------------------
    review_flags: list[dict] = []

    if dsa_result and dsa_result.get("requires_review"):
        matches = dsa_result.get("matches") or []
        reviewed = [m for m in matches if m.get("severity") not in (None, "strong")]
        target = reviewed[0] if reviewed else (matches[0] if matches else None)
        detail = (
            f"{(target.get('severity') or 'Moderate').capitalize()} DSA against HLA-{target.get('antigen')}"
            if target
            else "A weak or moderate donor-specific antibody was detected."
        )
        review_flags.append(
            {
                "code": REVIEW_FLAG_DSA_REQUIRES_REVIEW,
                "label": REVIEW_FLAG_LABELS[REVIEW_FLAG_DSA_REQUIRES_REVIEW],
                "detail": detail,
            }
        )

    if pra_bucket_result and pra_bucket_result.get("bucket_name") == HIGH_CPRA_BUCKET_NAME:
        percent = pra_bucket_result.get("percent")
        review_flags.append(
            {
                "code": REVIEW_FLAG_HIGH_CPRA,
                "label": REVIEW_FLAG_LABELS[REVIEW_FLAG_HIGH_CPRA],
                "detail": (
                    f"Calculated cPRA is {percent:.1f}%, in the {HIGH_CPRA_BUCKET_NAME} band."
                    if percent is not None
                    else f"Calculated cPRA is in the {HIGH_CPRA_BUCKET_NAME} band."
                ),
            }
        )

    # --- Row 4: completed, but no agreed risk level -----------------------
    if final_risk_level is None:
        review_flags.append(
            {
                "code": REVIEW_FLAG_UNCLASSIFIED_RISK,
                "label": REVIEW_FLAG_LABELS[REVIEW_FLAG_UNCLASSIFIED_RISK],
                "detail": (
                    "No doctor-specified point value exists yet for this cPRA range, so Step 7 "
                    "can't combine a final risk level."
                ),
            }
        )
        return ReportOutcome(
            verdict=VERDICT_PROCEED_CAUTION,
            verdict_label=VERDICT_LABELS[VERDICT_PROCEED_CAUTION],
            headline="Proceed with caution",
            detail=(
                "ABO, HLA mismatches, DSA and crossmatch all cleared for this pairing, but no "
                "risk band is defined yet for this cPRA range."
            ),
            risk_level=None,
            determined_at_step=7,
            total_steps=TOTAL_STEPS,
            action_required="Refer to the desensitisation protocol before scheduling.",
            review_flags=review_flags,
        )

    # --- Row 5: completed, review flags present ---------------------------
    if review_flags:
        return ReportOutcome(
            verdict=VERDICT_PROCEED_CAUTION,
            verdict_label=VERDICT_LABELS[VERDICT_PROCEED_CAUTION],
            headline="Proceed with caution",
            detail="This pairing cleared every gate, but one or more findings need review before scheduling.",
            risk_level=final_risk_level,
            determined_at_step=7,
            total_steps=TOTAL_STEPS,
            action_required="Refer to the desensitisation protocol before scheduling.",
            review_flags=review_flags,
        )

    # --- Row 6: completed, no flags ----------------------------------------
    return ReportOutcome(
        verdict=VERDICT_COMPATIBLE,
        verdict_label=VERDICT_LABELS[VERDICT_COMPATIBLE],
        headline="Compatible",
        detail=f"This pairing cleared every gate with a final risk level of {final_risk_level}.",
        risk_level=final_risk_level,
        determined_at_step=7,
        total_steps=TOTAL_STEPS,
        action_required=None,
        review_flags=[],
    )

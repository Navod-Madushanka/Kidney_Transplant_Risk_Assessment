"""add outcome to match_reports

Revision ID: 7a8b6052701d
Revises: a9d3f6c1b8e4
Create Date: 2026-08-09 21:00:00.000000

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '7a8b6052701d'
down_revision: Union[str, Sequence[str], None] = 'a9d3f6c1b8e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deliberately copied from app.reference_data.report_outcome /
# app.services.report_outcome_service rather than imported -- same
# discipline c3a7e4f2b8d5 and a9d3f6c1b8e4 already use for their backfills:
# a migration must keep producing the same result even if the live decision
# table is later refactored. If report_outcome.py's verdicts or decision
# table ever change, this frozen copy must NOT be updated to match --
# that's the point.
VERDICT_NOT_COMPATIBLE = "not_compatible"
VERDICT_CANNOT_ASSESS = "cannot_assess"
VERDICT_PROCEED_CAUTION = "proceed_with_caution"
VERDICT_COMPATIBLE = "compatible"

VERDICT_LABELS = {
    VERDICT_NOT_COMPATIBLE: "Not Compatible",
    VERDICT_CANNOT_ASSESS: "Cannot Assess",
    VERDICT_PROCEED_CAUTION: "Proceed with Caution",
    VERDICT_COMPATIBLE: "Compatible",
}

HALTED_STATUSES = (
    "halted_abo_fail",
    "halted_mismatch_reject",
    "halted_dsa_trigger",
    "halted_crossmatch_positive",
)

HALT_STEP_BY_STATUS = {
    "halted_abo_fail": 1,
    "halted_mismatch_reject": 3,
    "halted_dsa_trigger": 5,
    "halted_crossmatch_positive": 6,
}

HIGH_CPRA_BUCKET_NAME = ">60%"
TOTAL_STEPS = 7


def _halted_headline_and_detail(overall_status, abo_result, mismatch_result, dsa_result):
    if overall_status == "halted_abo_fail":
        recipient_type = (abo_result or {}).get("recipient_type", "unknown")
        donor_type = (abo_result or {}).get("donor_type", "unknown")
        return (
            "ABO incompatible",
            f"Recipient blood type {recipient_type} is not compatible with donor type {donor_type}.",
        )
    if overall_status == "halted_mismatch_reject":
        total = (mismatch_result or {}).get("total_mismatches", "unknown")
        bucket = (mismatch_result or {}).get("bucket_name", "unknown")
        return (
            "Too many HLA mismatches",
            f"{total} HLA mismatches across A/B/DRB1 (bucket: {bucket}) — above the acceptable threshold.",
        )
    if overall_status == "halted_dsa_trigger":
        matches = (dsa_result or {}).get("matches") or []
        strong = [m for m in matches if m.get("severity") not in ("weak", "moderate")]
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


def _build_outcome(overall_status, abo_result, mismatch_result, pra_bucket_result, dsa_result, final_risk_level):
    if overall_status in HALTED_STATUSES:
        headline, detail = _halted_headline_and_detail(overall_status, abo_result, mismatch_result, dsa_result)
        return {
            "verdict": VERDICT_NOT_COMPATIBLE,
            "verdict_label": VERDICT_LABELS[VERDICT_NOT_COMPATIBLE],
            "headline": headline,
            "detail": detail,
            "risk_level": None,
            "determined_at_step": HALT_STEP_BY_STATUS[overall_status],
            "total_steps": TOTAL_STEPS,
            "action_required": (
                "This donor cannot proceed. Add the patient to the paired exchange pool, "
                "or search for another donor."
            ),
            "review_flags": [],
        }

    if overall_status == "pending_crossmatch":
        return {
            "verdict": VERDICT_CANNOT_ASSESS,
            "verdict_label": VERDICT_LABELS[VERDICT_CANNOT_ASSESS],
            "headline": "Awaiting crossmatch",
            "detail": (
                "Every gate through Step 5 (ABO, mismatches, DSA) passed, but no crossmatch "
                "result was submitted with this check."
            ),
            "risk_level": None,
            "determined_at_step": 6,
            "total_steps": TOTAL_STEPS,
            "action_required": "Submit a crossmatch result and re-run the check.",
            "review_flags": [],
        }

    if overall_status != "completed":
        return {
            "verdict": VERDICT_CANNOT_ASSESS,
            "verdict_label": VERDICT_LABELS[VERDICT_CANNOT_ASSESS],
            "headline": "Unknown status",
            "detail": f"Unrecognized overall_status '{overall_status}'.",
            "risk_level": None,
            "determined_at_step": 0,
            "total_steps": TOTAL_STEPS,
            "action_required": None,
            "review_flags": [],
        }

    data_completeness = (mismatch_result or {}).get("data_completeness", True)
    if data_completeness is False:
        missing_inputs = (mismatch_result or {}).get("missing_inputs") or []
        flag = {
            "code": "incomplete_typing",
            "label": "Incomplete HLA typing",
            "detail": f"Missing: {', '.join(missing_inputs)}." if missing_inputs else "HLA typing is incomplete.",
        }
        action_required = (
            f"Enter the {missing_inputs[0]}, then re-run the check."
            if missing_inputs
            else "Complete HLA typing, then re-run the check."
        )
        return {
            "verdict": VERDICT_CANNOT_ASSESS,
            "verdict_label": VERDICT_LABELS[VERDICT_CANNOT_ASSESS],
            "headline": "Incomplete HLA typing",
            "detail": (
                f"{', '.join(missing_inputs)} missing — the mismatch count is a conservative "
                "worst-case estimate, not a confirmed result."
                if missing_inputs
                else "HLA typing is incomplete for one or more required loci."
            ),
            "risk_level": None,
            "determined_at_step": 3,
            "total_steps": TOTAL_STEPS,
            "action_required": action_required,
            "review_flags": [flag],
        }

    review_flags = []

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
            {"code": "dsa_requires_review", "label": "Donor-specific antibody detected", "detail": detail}
        )

    if pra_bucket_result and pra_bucket_result.get("bucket_name") == HIGH_CPRA_BUCKET_NAME:
        percent = pra_bucket_result.get("percent")
        review_flags.append(
            {
                "code": "high_cpra",
                "label": "Recipient is highly sensitised",
                "detail": (
                    f"Calculated cPRA is {percent:.1f}%, in the {HIGH_CPRA_BUCKET_NAME} band."
                    if percent is not None
                    else f"Calculated cPRA is in the {HIGH_CPRA_BUCKET_NAME} band."
                ),
            }
        )

    if final_risk_level is None:
        review_flags.append(
            {
                "code": "unclassified_risk",
                "label": "No agreed risk band for this cPRA range",
                "detail": (
                    "No doctor-specified point value exists yet for this cPRA range, so Step 7 "
                    "can't combine a final risk level."
                ),
            }
        )
        return {
            "verdict": VERDICT_PROCEED_CAUTION,
            "verdict_label": VERDICT_LABELS[VERDICT_PROCEED_CAUTION],
            "headline": "Proceed with caution",
            "detail": (
                "ABO, HLA mismatches, DSA and crossmatch all cleared for this pairing, but no "
                "risk band is defined yet for this cPRA range."
            ),
            "risk_level": None,
            "determined_at_step": 7,
            "total_steps": TOTAL_STEPS,
            "action_required": "Refer to the desensitisation protocol before scheduling.",
            "review_flags": review_flags,
        }

    if review_flags:
        return {
            "verdict": VERDICT_PROCEED_CAUTION,
            "verdict_label": VERDICT_LABELS[VERDICT_PROCEED_CAUTION],
            "headline": "Proceed with caution",
            "detail": "This pairing cleared every gate, but one or more findings need review before scheduling.",
            "risk_level": final_risk_level,
            "determined_at_step": 7,
            "total_steps": TOTAL_STEPS,
            "action_required": "Refer to the desensitisation protocol before scheduling.",
            "review_flags": review_flags,
        }

    return {
        "verdict": VERDICT_COMPATIBLE,
        "verdict_label": VERDICT_LABELS[VERDICT_COMPATIBLE],
        "headline": "Compatible",
        "detail": f"This pairing cleared every gate with a final risk level of {final_risk_level}.",
        "risk_level": final_risk_level,
        "determined_at_step": 7,
        "total_steps": TOTAL_STEPS,
        "action_required": None,
        "review_flags": [],
    }


def upgrade() -> None:
    """Upgrade schema.

    Adds the nullable `outcome` JSONB column, then backfills every existing
    row by recomputing its outcome from the already-stored step results,
    using a frozen copy of the decision table (see the module comment
    above) rather than importing app.services.report_outcome_service, so a
    later change to that live logic can't silently reinterpret what this
    migration produced for pre-existing reports.
    """
    op.add_column('match_reports', sa.Column('outcome', JSONB(), nullable=True))

    bind = op.get_bind()
    existing_rows = bind.execute(
        sa.text(
            "SELECT id, overall_status, abo_result, mismatch_result, pra_bucket_result, "
            "dsa_result, final_risk_level FROM match_reports"
        )
    ).fetchall()

    for row in existing_rows:
        outcome = _build_outcome(
            row.overall_status,
            row.abo_result,
            row.mismatch_result,
            row.pra_bucket_result,
            row.dsa_result,
            row.final_risk_level,
        )
        bind.execute(
            sa.text("UPDATE match_reports SET outcome = :outcome WHERE id = :id"),
            {"outcome": json.dumps(outcome), "id": row.id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('match_reports', 'outcome')

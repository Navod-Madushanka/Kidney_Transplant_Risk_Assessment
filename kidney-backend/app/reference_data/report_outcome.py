# app/reference_data/report_outcome.py
"""
Headline outcome shown at the top of a match report and in list views
(dashboard, patient detail). Added because `final_risk_level` alone left
most reports without any single readable answer: it's only ever set on a
`completed` check with both Step 3 and Step 4 buckets scored, so the four
`halted_*` statuses, `pending_crossmatch`, and even some `completed` checks
(incomplete typing, or cPRA in the ">60%" band with no agreed point value —
see risk_classification.py) rendered nothing but seven step cards.

This module defines the four possible verdicts and the decision table that
maps an `overall_status` plus a few pipeline results to one of them. It is
pure mapping — no clinical thresholds live here beyond what's already
established elsewhere (mismatch_buckets.py, dsa_threshold.py,
pra_buckets.py, risk_classification.py). Anything this module can't decide
from those existing values returns `cannot_assess` or leaves a field `None`
rather than guessing.

Exactly four verdicts, deliberately no fifth and no numeric composite score:
a single 0-100 number across ABO/mismatch/DSA/crossmatch/cPRA would imply a
precision and a set of relative weights this pipeline has no clinical basis
for. `final_risk_level` (the existing four-level scale from
risk_classification.py) is preserved as-is and surfaced alongside the
verdict, not replaced by it.

Decision table (first match wins — see build_report_outcome in
app/services/report_outcome_service.py for the implementation):

  1. overall_status is one of the four halted_* values  -> not_compatible
  2. overall_status == "pending_crossmatch"              -> cannot_assess
  3. completed AND mismatch_result.data_completeness is False -> cannot_assess
  4. completed AND final_risk_level is None              -> proceed_with_caution
     (this is a missing *policy* decision — no agreed point value for the
     cPRA ">60%" band — not missing clinical data: every pair-specific gate,
     ABO/mismatch/DSA/crossmatch, already passed for this exact donor. See
     risk_classification.py's PRA_BUCKET_POINTS docstring.)
  5. completed AND any review flag present               -> proceed_with_caution
  6. completed, otherwise                                 -> compatible
"""
from dataclasses import dataclass, field
from typing import Optional

VERDICT_NOT_COMPATIBLE = "not_compatible"
VERDICT_CANNOT_ASSESS = "cannot_assess"
VERDICT_PROCEED_CAUTION = "proceed_with_caution"
VERDICT_COMPATIBLE = "compatible"

VERDICT_LABELS: dict[str, str] = {
    VERDICT_NOT_COMPATIBLE: "Not Compatible",
    VERDICT_CANNOT_ASSESS: "Cannot Assess",
    VERDICT_PROCEED_CAUTION: "Proceed with Caution",
    VERDICT_COMPATIBLE: "Compatible",
}

# overall_status values that halt the pipeline outright (Steps 1/3/5/6) —
# every one of these means this specific pairing was rejected, so they all
# map to the same verdict. Kept as its own constant, not inlined, so
# match_pipeline.py's halt statuses and this table can't silently drift
# apart from each other.
HALTED_STATUSES: tuple[str, ...] = (
    "halted_abo_fail",
    "halted_mismatch_reject",
    "halted_dsa_trigger",
    "halted_crossmatch_positive",
)

REVIEW_FLAG_INCOMPLETE_TYPING = "incomplete_typing"
REVIEW_FLAG_DSA_REQUIRES_REVIEW = "dsa_requires_review"
REVIEW_FLAG_HIGH_CPRA = "high_cpra"
REVIEW_FLAG_UNCLASSIFIED_RISK = "unclassified_risk"
REVIEW_FLAG_UNMAPPED_ANTIBODY = "unmapped_antibody"

REVIEW_FLAG_LABELS: dict[str, str] = {
    REVIEW_FLAG_INCOMPLETE_TYPING: "Incomplete HLA typing",
    REVIEW_FLAG_DSA_REQUIRES_REVIEW: "Donor-specific antibody detected",
    REVIEW_FLAG_HIGH_CPRA: "Recipient is highly sensitised",
    REVIEW_FLAG_UNCLASSIFIED_RISK: "No agreed risk band for this cPRA range",
    REVIEW_FLAG_UNMAPPED_ANTIBODY: "Antibody could not be matched against donor typing",
}

# The cPRA bucket name that raises REVIEW_FLAG_HIGH_CPRA — must match the
# ">60%" bucket defined in app/reference_data/pra_buckets.py; not imported
# from there directly to avoid a reference_data -> reference_data import
# for what is, here, just a string comparison key.
HIGH_CPRA_BUCKET_NAME = ">60%"


@dataclass(frozen=True)
class ReviewFlag:
    code: str
    label: str
    detail: str


@dataclass(frozen=True)
class ReportOutcome:
    verdict: str
    verdict_label: str
    headline: str
    detail: str
    risk_level: Optional[str]
    determined_at_step: int
    total_steps: int
    action_required: Optional[str]
    review_flags: list[dict] = field(default_factory=list)


TOTAL_STEPS = 7

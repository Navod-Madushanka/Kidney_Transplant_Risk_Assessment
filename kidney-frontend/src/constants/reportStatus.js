// src/constants/reportStatus.js
//
// Single source of truth for how a MatchReport's overall_status and
// final_risk_level map to badge colors and human-readable labels, used
// across the dashboard patient list, recent reports list, the halted-
// report alert banner, the patient detail page, and the report detail
// page. Before this file existed, four separate components each had their
// own copy of this mapping (DashboardPage, RecentReportRow,
// HaltedReportBanner, PatientDetailPage) — easy to update one and miss the
// others. That's exactly what would have happened silently when Step 6's
// crossmatch gate and Steps 3/4's new reject statuses were added: only the
// components touched here know about them.

// Every status the sequential pipeline can halt on before reaching a final
// classification. Mirrors the halt statuses in
// kidney-backend/app/services/match_pipeline.py. Step 4 (cPRA) is
// deliberately NOT here — cPRA is population-level, not pair-specific, so
// it's informational only and never halts the pipeline (reverted
// 2026-08-08 after briefly being a reject gate; see match_pipeline.py's
// module docstring).
export const HALTED_STATUSES = new Set([
  "halted_abo_fail",
  "halted_dsa_trigger",
  "halted_mismatch_reject",
  "halted_crossmatch_positive",
])

// Not a rejection — every gate through Step 5 passed, but no crossmatch
// result was submitted with the check, so Steps 6/7 never ran. Distinct
// from HALTED_STATUSES because nothing here failed; the check is just
// incomplete.
export const PENDING_CROSSMATCH_STATUS = "pending_crossmatch"

// Short badge label per halted status (dashboard rows, patient detail list).
const HALT_BADGE_LABELS = {
  halted_abo_fail: "ABO Fail",
  halted_dsa_trigger: "DSA Halt",
  halted_mismatch_reject: "Mismatch Reject",
  halted_crossmatch_positive: "Crossmatch Positive",
}

// Longer, doctor-facing description of what halted the check — used as
// the headline on the report detail page's halt banner.
export const HALT_DESCRIPTIONS = {
  halted_abo_fail: "ABO incompatible",
  halted_dsa_trigger: "Donor-specific antibody detected",
  halted_mismatch_reject: "HLA mismatch count above this system's configured threshold",
  halted_crossmatch_positive: "Positive crossmatch",
}

// T7: mismatch_result.bucket_name is a stored value (kidney-backend/app/
// reference_data/mismatch_buckets.py — MatchReport JSONB, and a lookup key
// in risk_classification.py), so it can't be renamed. Displayed as-is,
// "<3 mismatches" misreads as covering 0 too (which has its own bucket
// right above it) — this is a *display* label only. Mirrors
// mismatch_bucket_display_label() in mismatch_buckets.py; keep both in sync.
const MISMATCH_BUCKET_DISPLAY_LABELS = {
  "0 mismatches": "0 mismatches",
  "<3 mismatches": "1-2 mismatches",
  "3-6 mismatches": "3-6 mismatches",
}

export function mismatchBucketDisplayLabel(bucketName) {
  return MISMATCH_BUCKET_DISPLAY_LABELS[bucketName] ?? bucketName
}

// Step 7's final classification
// (kidney-backend/app/reference_data/risk_classification.py) — the label
// set doctors actually asked for. Distinct from the legacy continuous-score
// risk tier below, which the sequential pipeline no longer uses for
// gating but still computes and returns for reference during the
// transition (see match_pipeline.py's module docstring).
const FINAL_RISK_LEVEL_TO_BADGE_STATUS = {
  "Low Risk": "low",
  "Low-Average Risk": "moderate",
  "High-Average Risk": "high-moderate",
  "High Risk": "high-risk",
}

// Maps each of the four report.outcome.verdict values (see
// kidney-backend/app/reference_data/report_outcome.py) to a <Badge> status
// key. "cannot_assess" deliberately maps to "pending" (the accent token),
// never to "halt"/"fail" (high-risk red) — cannot_assess means "the system
// doesn't know yet," not "rejected," and painting it red told doctors the
// opposite of what actually happened. See ReportDetailPage's verdict hero
// for the same rule applied to the full-size verdict card.
const VERDICT_TO_BADGE_STATUS = {
  not_compatible: "halt",
  cannot_assess: "pending",
  proceed_with_caution: "moderate",
  compatible: "clear",
}

/**
 * Given a report (or dashboard summary) with an `outcome` object (see
 * report_outcome.py's ReportOutcome), returns the {status, label} pair to
 * feed straight into <Badge>.
 *
 * Reads report.outcome.verdict / risk_level directly rather than
 * re-deriving clinical precedence from overall_status/dsa_result/
 * final_risk_level here in the frontend — that derivation now lives in one
 * place, app/services/report_outcome_service.py, so this file and the
 * report detail page can't drift apart on what counts as "compatible" vs
 * "needs review." When a risk_level is present (compatible, or proceed-
 * with-caution reports that still carry a Step 7 classification), the
 * label shows that specific level for extra precision in list views; the
 * badge color still follows the verdict, not the risk tier, since a
 * "High-Average Risk" pairing that ALSO has an open review flag must not
 * look identical to one that cleared every gate clean.
 *
 * Falls back to the old overall_status/dsa_result-derived logic only when
 * `report.outcome` is null (e.g. a report from before this field existed,
 * pre-backfill, or a lighter payload that never attached one) so every
 * caller keeps working during the transition.
 *
 * Usage:
 *   const { status, label } = reportBadgeProps(report)
 *   <Badge status={status}>{label}</Badge>
 */
export function reportBadgeProps(report) {
  if (!report) return { status: "neutral", label: "No check yet" }

  if (report.outcome) {
    const { verdict, verdict_label: verdictLabel, risk_level: riskLevel } = report.outcome
    const status = VERDICT_TO_BADGE_STATUS[verdict] ?? "neutral"
    if (riskLevel) {
      return {
        status: verdict === "compatible" ? FINAL_RISK_LEVEL_TO_BADGE_STATUS[riskLevel] ?? status : status,
        label: riskLevel,
      }
    }
    return { status, label: verdictLabel ?? verdict }
  }

  // --- Fallback for reports with no outcome attached -----------------------
  if (HALTED_STATUSES.has(report.overall_status)) {
    return { status: "halt", label: HALT_BADGE_LABELS[report.overall_status] }
  }

  if (report.overall_status === PENDING_CROSSMATCH_STATUS) {
    return { status: "pending", label: "Awaiting Crossmatch" }
  }

  if (report.dsa_result?.requires_review) {
    return { status: "pending", label: "DSA Review" }
  }

  if (report.final_risk_level) {
    return {
      status: FINAL_RISK_LEVEL_TO_BADGE_STATUS[report.final_risk_level] ?? "neutral",
      label: report.final_risk_level,
    }
  }

  if (report.overall_status === "completed") {
    return { status: "pending", label: "Cannot Assess" }
  }

  return { status: "neutral", label: "—" }
}

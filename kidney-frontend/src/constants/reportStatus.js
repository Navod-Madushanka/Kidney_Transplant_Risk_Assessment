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
// kidney-backend/app/services/match_pipeline.py. Step 4 (PRA/cPRA) is
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
  halted_mismatch_reject: "Too many HLA mismatches",
  halted_crossmatch_positive: "Positive crossmatch",
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

/**
 * Given a report (or dashboard summary) with `overall_status` and, where
 * available, `final_risk_level`, returns the {status, label} pair to feed
 * straight into <Badge>.
 *
 * Precedence: a halted status always wins (it's the most important thing
 * to surface) > pending-crossmatch > a weak/moderate DSA flagged for
 * desensitization review (Step 5, see dsa_result.requires_review — present
 * only on full report payloads, not the dashboard's lighter summary
 * objects) > Step 7's final_risk_level > a "Cannot Assess" placeholder for
 * a completed report that reached Step 7 without enough to classify > a
 * neutral "no check yet" placeholder.
 *
 * Deliberately does NOT fall back to the legacy score-derived `risk_tier`
 * (kidney-backend/app/reference_data/risk_tiers.py) the way this used to.
 * That field is only ever non-null on a report that reached Step 7 (see
 * match_pipeline.py) — so on exactly the reports where `final_risk_level`
 * is null, `risk_tier` would silently paint a specific colored risk badge
 * (e.g. "Moderate Risk") on a check Step 7 explicitly declined to classify,
 * contradicting the "Cannot assess" explanation shown in the report body.
 * `risk_tier` is still computed and returned by the API as a legacy
 * reference figure (see ReportDetailPage's "Legacy scoring" section), it's
 * just no longer trusted to stand in for a real answer here.
 *
 * Usage:
 *   const { status, label } = reportBadgeProps(report)
 *   <Badge status={status}>{label}</Badge>
 */
export function reportBadgeProps(report) {
  if (!report) return { status: "neutral", label: "No check yet" }

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

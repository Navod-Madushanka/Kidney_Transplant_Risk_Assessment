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

// Legacy continuous HLA score tier
// (kidney-backend/app/reference_data/risk_tiers.py) — kept only as a
// fallback for reports where Step 7 has no answer yet (most often:
// insufficient cPRA population sample), so there's still some signal
// rather than a bare "—".
const LEGACY_RISK_TIER_TO_BADGE_STATUS = {
  "Low Risk": "low",
  "Moderate Risk": "moderate",
  "High-Moderate Risk": "high-moderate",
  "High Genetic Risk": "high-risk",
}

/**
 * Given a report (or dashboard summary) with `overall_status` and,
 * where available, `final_risk_level` and/or the legacy `risk_tier`,
 * returns the {status, label} pair to feed straight into <Badge>.
 *
 * Precedence: a halted status always wins (it's the most important thing
 * to surface) > pending-crossmatch > Step 7's final_risk_level > the
 * legacy score-derived risk_tier > a neutral "no check yet" placeholder.
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

  if (report.final_risk_level) {
    return {
      status: FINAL_RISK_LEVEL_TO_BADGE_STATUS[report.final_risk_level] ?? "neutral",
      label: report.final_risk_level,
    }
  }

  if (report.risk_tier) {
    return {
      status: LEGACY_RISK_TIER_TO_BADGE_STATUS[report.risk_tier] ?? "neutral",
      label: report.risk_tier,
    }
  }

  return { status: "neutral", label: "—" }
}

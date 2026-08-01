// src/constants/reportStatus.test.js
import { describe, expect, it } from "vitest"
import {
  HALTED_STATUSES,
  PENDING_CROSSMATCH_STATUS,
  reportBadgeProps,
} from "./reportStatus"

describe("reportBadgeProps", () => {
  it("returns a neutral placeholder when there's no report at all", () => {
    expect(reportBadgeProps(null)).toEqual({ status: "neutral", label: "No check yet" })
    expect(reportBadgeProps(undefined)).toEqual({ status: "neutral", label: "No check yet" })
  })

  it.each([
    ["halted_abo_fail", "ABO Fail"],
    ["halted_dsa_trigger", "DSA Halt"],
    ["halted_mismatch_reject", "Mismatch Reject"],
    ["halted_pra_reject", "PRA Reject"],
    ["halted_crossmatch_positive", "Crossmatch Positive"],
  ])("labels %s as a halt, even if final_risk_level is somehow also present", (status, label) => {
    // A halted report should never carry a final_risk_level in practice
    // (the pipeline returns before Step 7 runs) — this guards that a halt
    // always wins regardless, since it's the most important thing to show.
    const badge = reportBadgeProps({ overall_status: status, final_risk_level: "Low Risk" })

    expect(badge).toEqual({ status: "halt", label })
  })

  it("labels pending_crossmatch as an awaiting-action badge, not a halt", () => {
    const badge = reportBadgeProps({ overall_status: PENDING_CROSSMATCH_STATUS })

    expect(badge).toEqual({ status: "pending", label: "Awaiting Crossmatch" })
    expect(HALTED_STATUSES.has(PENDING_CROSSMATCH_STATUS)).toBe(false)
  })

  it("prefers the Step 7 final_risk_level over the legacy risk_tier when both are present", () => {
    const badge = reportBadgeProps({
      overall_status: "completed",
      final_risk_level: "High Risk",
      risk_tier: "Low Risk",
    })

    expect(badge).toEqual({ status: "high-risk", label: "High Risk" })
  })

  it("falls back to the legacy risk_tier when final_risk_level is null", () => {
    // Real case: insufficient cPRA population data means Step 7 has no
    // answer, but the legacy 9-locus score may still be available.
    const badge = reportBadgeProps({
      overall_status: "completed",
      final_risk_level: null,
      risk_tier: "High-Moderate Risk",
    })

    expect(badge).toEqual({ status: "high-moderate", label: "High-Moderate Risk" })
  })

  it("falls back to a neutral placeholder when neither risk field is available", () => {
    const badge = reportBadgeProps({ overall_status: "completed" })

    expect(badge).toEqual({ status: "neutral", label: "—" })
  })

  it.each([
    ["Low Risk", "low"],
    ["Low-Average Risk", "moderate"],
    ["High-Average Risk", "high-moderate"],
    ["High Risk", "high-risk"],
  ])("maps final_risk_level %s to badge status %s", (finalRiskLevel, expectedStatus) => {
    const badge = reportBadgeProps({ overall_status: "completed", final_risk_level: finalRiskLevel })

    expect(badge.status).toBe(expectedStatus)
  })
})

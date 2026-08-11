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

  describe("with report.outcome present", () => {
    it("labels not_compatible as a halt", () => {
      const badge = reportBadgeProps({
        overall_status: "halted_abo_fail",
        outcome: { verdict: "not_compatible", verdict_label: "Not Compatible", risk_level: null },
      })

      expect(badge).toEqual({ status: "halt", label: "Not Compatible" })
    })

    it("labels cannot_assess with the accent/pending token, never a halt color", () => {
      // The single most important rule here: cannot_assess means "the
      // system doesn't know yet," the opposite of "rejected" — it must
      // never render with the same red used for not_compatible.
      const badge = reportBadgeProps({
        overall_status: "pending_crossmatch",
        outcome: { verdict: "cannot_assess", verdict_label: "Cannot Assess", risk_level: null },
      })

      expect(badge).toEqual({ status: "pending", label: "Cannot Assess" })
      expect(badge.status).not.toBe("halt")
    })

    it("labels proceed_with_caution as moderate, using the risk level as the label when present", () => {
      const badge = reportBadgeProps({
        overall_status: "completed",
        outcome: {
          verdict: "proceed_with_caution",
          verdict_label: "Proceed with Caution",
          risk_level: "Low-Average Risk",
        },
      })

      expect(badge).toEqual({ status: "moderate", label: "Low-Average Risk" })
    })

    it("labels proceed_with_caution with the verdict label when no risk level is set (row 4: unclassified cPRA band)", () => {
      const badge = reportBadgeProps({
        overall_status: "completed",
        outcome: { verdict: "proceed_with_caution", verdict_label: "Proceed with Caution", risk_level: null },
      })

      expect(badge).toEqual({ status: "moderate", label: "Proceed with Caution" })
    })

    it("labels compatible using the specific final risk level's own color, not a generic clear color", () => {
      const badge = reportBadgeProps({
        overall_status: "completed",
        outcome: { verdict: "compatible", verdict_label: "Compatible", risk_level: "High Risk" },
      })

      expect(badge).toEqual({ status: "high-risk", label: "High Risk" })
    })

    it("ignores overall_status/dsa_result entirely once outcome is present", () => {
      // Regression guard: outcome is now the single source of truth: a
      // report with a stale/contradictory overall_status or dsa_result
      // must not leak back into the badge once outcome has decided.
      const badge = reportBadgeProps({
        overall_status: "halted_abo_fail",
        dsa_result: { requires_review: true },
        outcome: { verdict: "compatible", verdict_label: "Compatible", risk_level: "Low Risk" },
      })

      expect(badge).toEqual({ status: "low", label: "Low Risk" })
    })
  })

  describe("fallback when report.outcome is null", () => {
    it.each([
      ["halted_abo_fail", "ABO Fail"],
      ["halted_dsa_trigger", "DSA Halt"],
      ["halted_mismatch_reject", "Mismatch Reject"],
      ["halted_crossmatch_positive", "Crossmatch Positive"],
    ])("labels %s as a halt, even if final_risk_level is somehow also present", (status, label) => {
      const badge = reportBadgeProps({ overall_status: status, final_risk_level: "Low Risk", outcome: null })

      expect(badge).toEqual({ status: "halt", label })
    })

    it("labels pending_crossmatch as an awaiting-action badge, not a halt", () => {
      const badge = reportBadgeProps({ overall_status: PENDING_CROSSMATCH_STATUS, outcome: null })

      expect(badge).toEqual({ status: "pending", label: "Awaiting Crossmatch" })
      expect(HALTED_STATUSES.has(PENDING_CROSSMATCH_STATUS)).toBe(false)
    })

    it("flags a completed report as needing DSA review when a weak/moderate DSA was found", () => {
      const badge = reportBadgeProps({
        overall_status: "completed",
        final_risk_level: "Low Risk",
        dsa_result: { is_halted: false, requires_review: true },
        outcome: null,
      })

      expect(badge).toEqual({ status: "pending", label: "DSA Review" })
    })

    it("does not flag DSA review when dsa_result is absent (dashboard summary payloads)", () => {
      const badge = reportBadgeProps({ overall_status: "completed", final_risk_level: "Low Risk", outcome: null })

      expect(badge).toEqual({ status: "low", label: "Low Risk" })
    })

    it("falls back to a neutral placeholder when overall_status has no known mapping", () => {
      const badge = reportBadgeProps({ overall_status: "some_future_status", outcome: null })

      expect(badge).toEqual({ status: "neutral", label: "—" })
    })

    it("falls back to Cannot Assess when a completed report has no risk field available", () => {
      const badge = reportBadgeProps({ overall_status: "completed", outcome: null })

      expect(badge).toEqual({ status: "pending", label: "Cannot Assess" })
    })

    it.each([
      ["Low Risk", "low"],
      ["Low-Average Risk", "moderate"],
      ["High-Average Risk", "high-moderate"],
      ["High Risk", "high-risk"],
    ])("maps final_risk_level %s to badge status %s", (finalRiskLevel, expectedStatus) => {
      const badge = reportBadgeProps({ overall_status: "completed", final_risk_level: finalRiskLevel, outcome: null })

      expect(badge.status).toBe(expectedStatus)
    })
  })
})

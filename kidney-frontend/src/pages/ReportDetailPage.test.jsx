// src/pages/ReportDetailPage.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import ReportDetailPage from "./ReportDetailPage"
import { getReport } from "../api/reports"
import { ReviewedReportsContext } from "../context/ReviewedReportsContext"

vi.mock("../api/reports")

const BASE_REPORT = {
  id: "11111111-1111-1111-1111-111111111111",
  patient_id: "22222222-2222-2222-2222-222222222222",
  donor_id: "33333333-3333-3333-3333-333333333333",
  abo_result: { is_compatible: true, recipient_type: "AB", donor_type: "O" },
  sensitization_result: null,
  mismatch_result: null,
  pra_bucket_result: null,
  dsa_result: null,
  crossmatch_result: null,
  hla_scoring_result: null,
  cpra_result: null,
  final_risk_level: null,
  created_at: "2026-08-09T12:00:00Z",
  updated_at: "2026-08-09T12:00:00Z",
}

function renderPage(report) {
  getReport.mockResolvedValue(report)

  return render(
    <ReviewedReportsContext.Provider value={{ markReviewed: vi.fn(), isReviewed: () => false }}>
      <MemoryRouter initialEntries={[`/reports/${report.id}`]}>
        <Routes>
          <Route path="/reports/:reportId" element={<ReportDetailPage />} />
        </Routes>
      </MemoryRouter>
    </ReviewedReportsContext.Provider>
  )
}

describe("ReportDetailPage — verdict hero", () => {
  it("renders the not_compatible verdict with the high-risk token", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "halted_abo_fail",
      abo_result: { is_compatible: false, recipient_type: "O", donor_type: "A" },
      outcome: {
        verdict: "not_compatible",
        verdict_label: "Not Compatible",
        headline: "ABO incompatible",
        detail: "Recipient blood type O is not compatible with donor type A.",
        risk_level: null,
        determined_at_step: 1,
        total_steps: 7,
        action_required: "This donor cannot proceed.",
        review_flags: [],
      },
    })

    const headings = await screen.findAllByText("Not Compatible")
    const hero = headings.find((el) => el.className.includes("text-[28px]"))
    expect(hero).toHaveClass("text-high-risk")
  })

  it("renders the cannot_assess verdict WITHOUT any high-risk class", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "pending_crossmatch",
      outcome: {
        verdict: "cannot_assess",
        verdict_label: "Cannot Assess",
        headline: "Awaiting crossmatch",
        detail: "Every gate through Step 5 passed, but no crossmatch result was submitted.",
        risk_level: null,
        determined_at_step: 6,
        total_steps: 7,
        action_required: "Submit a crossmatch result and re-run the check.",
        review_flags: [],
      },
    })

    const headings = await screen.findAllByText("Cannot Assess")
    const hero = headings.find((el) => el.className.includes("text-[28px]"))
    expect(hero.className).not.toMatch(/high-risk/)
    expect(hero).toHaveClass("text-accent")
  })

  it("renders the proceed_with_caution verdict with the moderate token", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "completed",
      final_risk_level: "Low Risk",
      outcome: {
        verdict: "proceed_with_caution",
        verdict_label: "Proceed with Caution",
        headline: "Proceed with caution",
        detail: "Cleared every gate, but one finding needs review.",
        risk_level: "Low Risk",
        determined_at_step: 7,
        total_steps: 7,
        action_required: "Refer to the desensitisation protocol before scheduling.",
        review_flags: [{ code: "dsa_requires_review", label: "Donor-specific antibody detected", detail: "Moderate DSA against HLA-B44" }],
      },
    })

    const heading = await screen.findByText("Proceed with Caution")
    expect(heading).toHaveClass("text-moderate")
  })

  it("renders the compatible verdict with the clear token", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "completed",
      final_risk_level: "Low Risk",
      outcome: {
        verdict: "compatible",
        verdict_label: "Compatible",
        headline: "Compatible",
        detail: "This pairing cleared every gate with a final risk level of Low Risk.",
        risk_level: "Low Risk",
        determined_at_step: 7,
        total_steps: 7,
        action_required: null,
        review_flags: [],
      },
    })

    const heading = await screen.findByText("Compatible")
    expect(heading).toHaveClass("text-clear")
  })
})

describe("ReportDetailPage — step timeline", () => {
  it("renders steps after a halt as 'Not evaluated', not a pass marker", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "halted_abo_fail",
      abo_result: { is_compatible: false, recipient_type: "O", donor_type: "A" },
      outcome: {
        verdict: "not_compatible",
        verdict_label: "Not Compatible",
        headline: "ABO incompatible",
        detail: "Recipient blood type O is not compatible with donor type A.",
        risk_level: null,
        determined_at_step: 1,
        total_steps: 7,
        action_required: "This donor cannot proceed.",
        review_flags: [],
      },
    })

    await screen.findByText("Pipeline steps")
    const notEvaluated = screen.getAllByText("Not evaluated")
    // Steps 2-7 never ran once ABO halted at step 1.
    expect(notEvaluated).toHaveLength(6)
  })

  it("collapses steps on mount and expands on click, flipping aria-expanded", async () => {
    const user = userEvent.setup()
    renderPage({
      ...BASE_REPORT,
      overall_status: "halted_abo_fail",
      abo_result: { is_compatible: false, recipient_type: "O", donor_type: "A" },
      outcome: {
        verdict: "not_compatible",
        verdict_label: "Not Compatible",
        headline: "ABO incompatible",
        detail: "Recipient blood type O is not compatible with donor type A.",
        risk_level: null,
        determined_at_step: 1,
        total_steps: 7,
        action_required: "This donor cannot proceed.",
        review_flags: [],
      },
    })

    const stepButton = await screen.findByRole("button", { name: /Step 1 — ABO compatibility/i })
    expect(stepButton).toHaveAttribute("aria-expanded", "false")

    await user.click(stepButton)
    expect(stepButton).toHaveAttribute("aria-expanded", "true")
  })
})

const CAUTION_OUTCOME = {
  verdict: "proceed_with_caution",
  verdict_label: "Proceed with Caution",
  headline: "Proceed with caution",
  detail: "Cleared every gate, but one finding needs review.",
  risk_level: "Low Risk",
  determined_at_step: 7,
  total_steps: 7,
  action_required: "Refer to the desensitisation protocol before scheduling.",
  review_flags: [],
}

const SUFFICIENT_LKDPI_RESULT = {
  score: 30.41,
  band: "moderate",
  band_label: "Moderate",
  has_sufficient_data: true,
  missing_inputs: [],
  contributions: [
    { label: "Donor systolic BP (130.0 mmHg)", points: 57.2 },
    { label: "Donor/recipient weight ratio (1.00, capped at 0.9)", points: -45.78 },
    { label: "Donor eGFR (90.0)", points: -34.29 },
    { label: "Donor BMI (25.0)", points: 29.25 },
    { label: "Donor age over 50 (60)", points: 18.5 },
    { label: "HLA-B mismatches (1)", points: 8.57 },
    { label: "HLA-DR mismatches (1)", points: 8.26 },
  ],
  values_outside_model_range: [],
  population_validated: true,
  population_extrapolation_disclaimer: null,
  model_limitation_note:
    "External C-statistic 0.55 in both European and Canadian validation cohorts (near-chance discrimination); never validated in any South Asian population.",
  source_citation: "Massie ME, Leanza J, Fahmy LM, et al. A Risk Index for Living Donor Kidney Transplantation.",
  single_factor_override: { label: "Donor systolic BP (130.0 mmHg)", points: 57.2, delta: 4.4 },
}

describe("ReportDetailPage — LKDPI score card", () => {
  it("is absent when the verdict is not_compatible", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "halted_abo_fail",
      abo_result: { is_compatible: false, recipient_type: "O", donor_type: "A" },
      lkdpi_result: SUFFICIENT_LKDPI_RESULT,
      outcome: {
        verdict: "not_compatible",
        verdict_label: "Not Compatible",
        headline: "ABO incompatible",
        detail: "Recipient blood type O is not compatible with donor type A.",
        risk_level: null,
        determined_at_step: 1,
        total_steps: 7,
        action_required: "This donor cannot proceed.",
        review_flags: [],
      },
    })

    await screen.findAllByText("Not Compatible")
    expect(screen.queryByText("LKDPI")).not.toBeInTheDocument()
  })

  it("renders the score, band, and component breakdown when the verdict allows it", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "completed",
      final_risk_level: "Low Risk",
      lkdpi_result: SUFFICIENT_LKDPI_RESULT,
      outcome: CAUTION_OUTCOME,
    })

    await screen.findByText("LKDPI")
    expect(screen.getByText("+30.4")).toBeInTheDocument()
    expect(screen.getByText("Moderate")).toBeInTheDocument()
    expect(screen.getAllByText(/Donor systolic BP \(130.0 mmHg\)/).length).toBeGreaterThan(0)
  })

  it("names the missing fields when has_sufficient_data is false", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "completed",
      final_risk_level: "Low Risk",
      lkdpi_result: {
        score: null,
        band: null,
        band_label: null,
        has_sufficient_data: false,
        missing_inputs: ["recipient weight", "donor race"],
        contributions: [],
        values_outside_model_range: [],
        population_validated: true,
        population_extrapolation_disclaimer: null,
        model_limitation_note: "External C-statistic 0.55.",
        source_citation: "Massie et al.",
        single_factor_override: null,
      },
      outcome: CAUTION_OUTCOME,
    })

    expect(await screen.findByText(/LKDPI not calculated/i)).toBeInTheDocument()
    expect(screen.getByText("recipient weight")).toBeInTheDocument()
    expect(screen.getByText("donor race")).toBeInTheDocument()
  })

  it("shows the model-limitation line outside any collapsed element", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "completed",
      final_risk_level: "Low Risk",
      lkdpi_result: SUFFICIENT_LKDPI_RESULT,
      outcome: CAUTION_OUTCOME,
    })

    await screen.findByText("LKDPI")
    // Not behind a toggle/disclosure — the limitation text must be present
    // and visible in the DOM immediately, not hidden until a "show more"
    // click (unlike the step timeline's collapsed detail panels).
    const limitationParagraph = document.querySelector(".limit, .border-t.border-border.bg-bg p")
    expect(document.body.textContent).toContain(SUFFICIENT_LKDPI_RESULT.model_limitation_note)
    expect(limitationParagraph).toBeVisible()
  })

  it("shows the single-factor override callout when one component exceeds +25", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "completed",
      final_risk_level: "Low Risk",
      lkdpi_result: SUFFICIENT_LKDPI_RESULT,
      outcome: CAUTION_OUTCOME,
    })

    expect(await screen.findByText(/One factor is driving this score/i)).toBeInTheDocument()
  })

  it("omits the single-factor override callout when no component exceeds the threshold", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "completed",
      final_risk_level: "Low Risk",
      lkdpi_result: { ...SUFFICIENT_LKDPI_RESULT, single_factor_override: null },
      outcome: CAUTION_OUTCOME,
    })

    await screen.findByText("LKDPI")
    expect(screen.queryByText(/One factor is driving this score/i)).not.toBeInTheDocument()
  })
})

describe("ReportDetailPage — fallback for a null outcome", () => {
  it("still renders via the fallback path when report.outcome is null", async () => {
    renderPage({
      ...BASE_REPORT,
      overall_status: "completed",
      final_risk_level: "Low Risk",
      outcome: null,
    })

    await waitFor(() => expect(getReport).toHaveBeenCalled())
    expect(await screen.findByText(/hasn't been backfilled yet/i)).toBeInTheDocument()
    expect(await screen.findByText("Pipeline steps")).toBeInTheDocument()
  })
})

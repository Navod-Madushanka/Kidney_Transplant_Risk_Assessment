// src/pages/ExchangePoolPage.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { getExchangeMatch } from "../api/exchange"
import ExchangePoolPage from "./ExchangePoolPage"

vi.mock("../api/exchange", () => ({ getExchangeMatch: vi.fn() }))

const NODE_A = {
  pair_id: "donor-a",
  donor_id: "donor-a",
  donor_blood_type: "B",
  donor_rh_factor: "+",
  donor_hospital_name: "First Test Hospital",
  donor_doctor_full_name: "Dr. First Doctor",
  donor_doctor_email: "first@example.com",
  patient_id: "patient-a",
  patient_blood_type: "A",
  patient_rh_factor: "+",
  patient_hospital_name: "First Test Hospital",
  patient_doctor_full_name: "Dr. First Doctor",
  patient_doctor_email: "first@example.com",
}

const NODE_B = {
  ...NODE_A,
  pair_id: "donor-b",
  donor_id: "donor-b",
  donor_blood_type: "A",
  patient_id: "patient-b",
  patient_blood_type: "B",
  donor_hospital_name: "Second Test Hospital",
  patient_hospital_name: "Second Test Hospital",
  donor_doctor_full_name: "Dr. Second Doctor",
  patient_doctor_full_name: "Dr. Second Doctor",
  donor_doctor_email: "second@example.com",
  patient_doctor_email: "second@example.com",
}

const MATCH_RESPONSE = {
  policy: "max_transplants",
  nodes: [NODE_A, NODE_B],
  edges: [
    { from_pair_id: "donor-a", to_pair_id: "donor-b", mismatch_result: {}, dsa_result: {} },
    { from_pair_id: "donor-b", to_pair_id: "donor-a", mismatch_result: {}, dsa_result: {} },
  ],
  selected_cycles: [{ pair_ids: ["donor-a", "donor-b"], weight: 2 }],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/exchange"]}>
      <Routes>
        <Route path="/exchange" element={<ExchangePoolPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe("ExchangePoolPage", () => {
  it("renders pool stats and the selected cycle once the match resolves", async () => {
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)

    renderPage()

    expect(await screen.findByText("Incompatible pairs")).toBeInTheDocument()
    expect(screen.getAllByText("2").length).toBeGreaterThan(0)
    expect(screen.getByText("#1")).toBeInTheDocument()
  })

  it("shows an empty-state message when the pool is empty", async () => {
    getExchangeMatch.mockResolvedValue({
      policy: "max_transplants",
      nodes: [],
      edges: [],
      selected_cycles: [],
    })

    renderPage()

    expect(
      await screen.findByText("No incompatible pairs in the exchange pool right now.")
    ).toBeInTheDocument()
  })

  it("shows an error message when the match request fails", async () => {
    getExchangeMatch.mockRejectedValue(new Error("boom"))

    renderPage()

    expect(
      await screen.findByText("Couldn't load the exchange pool. Please try refreshing.")
    ).toBeInTheDocument()
  })

  it("labels the selected-cycle count tile 'Cycles selected', not 'Cycles found'", async () => {
    // Review #2 bug 20: the API only ever returns the solver's already-
    // selected cycles, never a separate "candidates found" count.
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)

    renderPage()

    expect(await screen.findByText("Cycles selected")).toBeInTheDocument()
    expect(screen.queryByText("Cycles found")).not.toBeInTheDocument()
  })

  it("shows the loading spinner, not the stale error, when retrying the exact policy that previously failed", async () => {
    // Review #2 bug 23: failedPolicy used to only ever be set, never
    // cleared, so switching away and back to the SAME policy that had
    // failed once kept showing the old error message for the whole new
    // request (switching to a genuinely *different* policy already
    // worked before this fix, since failedPolicy simply wouldn't match
    // the new policy -- this test is specifically the same-policy retry).
    const user = userEvent.setup()
    let resolveRetry
    getExchangeMatch
      .mockRejectedValueOnce(new Error("boom")) // initial max_transplants load
      .mockResolvedValueOnce(MATCH_RESPONSE) // switch to max_quality
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRetry = () => resolve(MATCH_RESPONSE) // switch back to max_transplants
          })
      )

    renderPage()

    expect(
      await screen.findByText("Couldn't load the exchange pool. Please try refreshing.")
    ).toBeInTheDocument()

    const select = screen.getByLabelText("Optimization policy")
    await user.selectOptions(select, "max_quality")
    expect(await screen.findByText("Incompatible pairs")).toBeInTheDocument()

    await user.selectOptions(select, "max_transplants")
    // The retry for max_transplants is still pending -- must show the
    // spinner, not the stale error from the first max_transplants request.
    expect(
      screen.queryByText("Couldn't load the exchange pool. Please try refreshing.")
    ).not.toBeInTheDocument()
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument()

    resolveRetry()
    expect(await screen.findByText("Incompatible pairs")).toBeInTheDocument()
  })
})

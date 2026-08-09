// src/pages/ExchangePoolPage.test.jsx
import { render, screen } from "@testing-library/react"
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
})

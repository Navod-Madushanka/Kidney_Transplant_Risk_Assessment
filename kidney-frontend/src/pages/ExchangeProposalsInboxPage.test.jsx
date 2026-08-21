// src/pages/ExchangeProposalsInboxPage.test.jsx
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { decideExchangeProposalPair, listExchangeProposals } from "../api/exchangeProposals"
import ExchangeProposalsInboxPage from "./ExchangeProposalsInboxPage"

vi.mock("../api/exchangeProposals", () => ({
  listExchangeProposals: vi.fn(),
  decideExchangeProposalPair: vi.fn(),
  cancelExchangeProposal: vi.fn(),
}))
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "doctor-a" } }),
}))

const PROPOSAL = {
  id: "proposal-1",
  status: "proposed",
  policy: "max_transplants",
  weight: 2,
  expires_at: "2026-09-01T00:00:00Z",
  created_by_doctor_id: "doctor-a",
  cycle_snapshot: {
    nodes: [
      {
        pair_id: "donor-a",
        donor_blood_type: "B",
        donor_hospital_name: "First Hospital",
        donor_doctor_full_name: "Dr First",
        patient_blood_type: "A",
        patient_hospital_name: "First Hospital",
        patient_doctor_full_name: "Dr First",
      },
      {
        pair_id: "donor-b",
        donor_blood_type: "A",
        donor_hospital_name: "Second Hospital",
        donor_doctor_full_name: "Dr Second",
        patient_blood_type: "B",
        patient_hospital_name: "Second Hospital",
        patient_doctor_full_name: "Dr Second",
      },
    ],
    edges: [],
  },
  pairs: [
    { id: "pair-a", donor_id: "donor-a", owning_doctor_id: "doctor-a", decision: "pending" },
    { id: "pair-b", donor_id: "donor-b", owning_doctor_id: "doctor-b", decision: "pending" },
  ],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/exchange/proposals"]}>
      <Routes>
        <Route path="/exchange/proposals" element={<ExchangeProposalsInboxPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe("ExchangeProposalsInboxPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("defaults to the 'awaiting my decision' scope", async () => {
    listExchangeProposals.mockResolvedValue([PROPOSAL])

    renderPage()

    expect(await screen.findByText(/2 pairs/)).toBeInTheDocument()
    expect(listExchangeProposals).toHaveBeenCalledWith(true)
  })

  it("switches to all open proposals", async () => {
    listExchangeProposals.mockResolvedValue([PROPOSAL])
    const user = userEvent.setup()

    renderPage()
    await screen.findByText(/2 pairs/)

    await user.click(screen.getByRole("radio", { name: "All open proposals" }))

    expect(listExchangeProposals).toHaveBeenLastCalledWith(false)
  })

  it("shows an empty-state message when nothing is awaiting decision", async () => {
    listExchangeProposals.mockResolvedValue([])

    renderPage()

    expect(
      await screen.findByText("No proposals are awaiting your decision right now.")
    ).toBeInTheDocument()
  })

  it("accepts a pair I own and reloads the list", async () => {
    listExchangeProposals.mockResolvedValue([PROPOSAL])
    decideExchangeProposalPair.mockResolvedValue({ ...PROPOSAL })
    const user = userEvent.setup()

    renderPage()
    await screen.findByText(/2 pairs/)

    await user.click(screen.getByRole("button", { name: "Accept" }))
    const dialog = screen.getByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "Accept" }))

    expect(decideExchangeProposalPair).toHaveBeenCalledWith(
      "proposal-1", "pair-a", "accepted"
    )
    expect(listExchangeProposals).toHaveBeenCalledTimes(2)
  })

  it("shows an error message instead of failing silently when the decision fails", async () => {
    listExchangeProposals.mockResolvedValue([PROPOSAL])
    decideExchangeProposalPair.mockRejectedValue(new Error("Pair already decided."))
    const user = userEvent.setup()

    renderPage()
    await screen.findByText(/2 pairs/)

    await user.click(screen.getByRole("button", { name: "Accept" }))
    const dialog = screen.getByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "Accept" }))

    expect(await screen.findByText("Pair already decided.")).toBeInTheDocument()
  })

  it("shows Cancel proposal only for the proposal's own proposer", async () => {
    listExchangeProposals.mockResolvedValue([PROPOSAL])

    renderPage()
    await screen.findByText(/2 pairs/)

    // currentDoctorId ("doctor-a") matches created_by_doctor_id above.
    expect(screen.getByRole("button", { name: "Cancel proposal" })).toBeInTheDocument()
  })
})

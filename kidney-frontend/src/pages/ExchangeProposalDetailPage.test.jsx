// src/pages/ExchangeProposalDetailPage.test.jsx
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import {
  cancelExchangeProposal,
  decideExchangeProposalPair,
  getExchangeProposal,
} from "../api/exchangeProposals"
import ExchangeProposalDetailPage from "./ExchangeProposalDetailPage"

vi.mock("../api/exchangeProposals", () => ({
  getExchangeProposal: vi.fn(),
  decideExchangeProposalPair: vi.fn(),
  cancelExchangeProposal: vi.fn(),
}))

let mockUser = { id: "doctor-a" }
vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: mockUser }),
}))

function makeProposal(overrides = {}) {
  return {
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
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/exchange/proposals/proposal-1"]}>
      <Routes>
        <Route path="/exchange/proposals/:proposalId" element={<ExchangeProposalDetailPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe("ExchangeProposalDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUser = { id: "doctor-a" }
  })

  it("renders the full cycle chain with each pair's decision state", async () => {
    getExchangeProposal.mockResolvedValue(makeProposal())

    renderPage()

    expect(await screen.findByText("Exchange proposal")).toBeInTheDocument()
    expect(screen.getByText("↺ closes back to the first pair")).toBeInTheDocument()
    expect(screen.getAllByText("pending")).toHaveLength(2)
  })

  it("shows the sticky accept/decline bar only for a doctor with a pending pair of their own", async () => {
    getExchangeProposal.mockResolvedValue(makeProposal())
    renderPage()
    await screen.findByText("Exchange proposal")

    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Decline" })).toBeInTheDocument()
  })

  it("hides the action bar for a doctor with no pending pair in this proposal", async () => {
    mockUser = { id: "some-other-doctor" }
    getExchangeProposal.mockResolvedValue(makeProposal())

    renderPage()
    await screen.findByText("Exchange proposal")

    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument()
  })

  it("accepts via the sticky bar and reloads the proposal", async () => {
    getExchangeProposal.mockResolvedValue(makeProposal())
    decideExchangeProposalPair.mockResolvedValue(undefined)
    const user = userEvent.setup()

    renderPage()
    await screen.findByText("Exchange proposal")

    await user.click(screen.getByRole("button", { name: "Accept" }))
    const dialog = screen.getByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "Accept" }))

    expect(decideExchangeProposalPair).toHaveBeenCalledWith("proposal-1", "pair-a", "accepted", null)
    expect(getExchangeProposal).toHaveBeenCalledTimes(2)
  })

  it("shows an error message instead of failing silently when the decision fails", async () => {
    getExchangeProposal.mockResolvedValue(makeProposal())
    decideExchangeProposalPair.mockRejectedValue(new Error("Pair already decided."))
    const user = userEvent.setup()

    renderPage()
    await screen.findByText("Exchange proposal")

    await user.click(screen.getByRole("button", { name: "Accept" }))
    const dialog = screen.getByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "Accept" }))

    expect(await screen.findByText("Pair already decided.")).toBeInTheDocument()
  })

  it("sends the typed decline reason", async () => {
    getExchangeProposal.mockResolvedValue(makeProposal())
    decideExchangeProposalPair.mockResolvedValue(undefined)
    const user = userEvent.setup()

    renderPage()
    await screen.findByText("Exchange proposal")

    await user.type(
      screen.getByPlaceholderText("Decline reason (optional)"),
      "Recipient no longer eligible"
    )
    await user.click(screen.getByRole("button", { name: "Decline" }))
    const dialog = screen.getByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "Decline" }))

    expect(decideExchangeProposalPair).toHaveBeenCalledWith(
      "proposal-1", "pair-a", "declined", "Recipient no longer eligible"
    )
  })

  it("shows Cancel proposal for the proposer and calls the cancel endpoint", async () => {
    getExchangeProposal.mockResolvedValue(makeProposal())
    cancelExchangeProposal.mockResolvedValue(undefined)
    const user = userEvent.setup()

    renderPage()
    await screen.findByText("Exchange proposal")

    await user.click(screen.getByRole("button", { name: "Cancel proposal" }))

    expect(cancelExchangeProposal).toHaveBeenCalledWith("proposal-1")
  })

  it("shows an error message when the proposal fails to load", async () => {
    getExchangeProposal.mockRejectedValue(new Error("boom"))

    renderPage()

    expect(
      await screen.findByText("Couldn't load this proposal. Please try refreshing.")
    ).toBeInTheDocument()
  })
})

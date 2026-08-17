// src/components/domain/exchange/ExchangeProposalCard.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import ExchangeProposalCard from "./ExchangeProposalCard"

const NODE_A = {
  pair_id: "donor-a",
  donor_blood_type: "B",
  donor_hospital_name: "First Hospital",
  donor_doctor_full_name: "Dr First",
  patient_blood_type: "A",
  patient_hospital_name: "First Hospital",
  patient_doctor_full_name: "Dr First",
}

const NODE_B = {
  pair_id: "donor-b",
  donor_blood_type: "A",
  donor_hospital_name: "Second Hospital",
  donor_doctor_full_name: "Dr Second",
  patient_blood_type: "B",
  patient_hospital_name: "Second Hospital",
  patient_doctor_full_name: "Dr Second",
}

function makeProposal(overrides = {}) {
  return {
    id: "proposal-1",
    status: "proposed",
    policy: "max_transplants",
    weight: 2,
    expires_at: "2026-09-01T00:00:00Z",
    created_by_doctor_id: "doctor-a",
    cycle_snapshot: { nodes: [NODE_A, NODE_B], edges: [] },
    pairs: [
      {
        id: "pair-a",
        donor_id: "donor-a",
        owning_doctor_id: "doctor-a",
        decision: "pending",
      },
      {
        id: "pair-b",
        donor_id: "donor-b",
        owning_doctor_id: "doctor-b",
        decision: "pending",
      },
    ],
    ...overrides,
  }
}

function renderCard(props) {
  return render(
    <MemoryRouter>
      <ExchangeProposalCard proposal={makeProposal()} currentDoctorId="doctor-a" {...props} />
    </MemoryRouter>
  )
}

describe("ExchangeProposalCard", () => {
  it("renders the full chain with each pair's decision state", () => {
    renderCard()

    expect(screen.getByText(/2 pairs/)).toBeInTheDocument()
    expect(screen.getAllByText("Awaiting decision")).toHaveLength(2)
  })

  it("shows accept/decline for a pending pair the current doctor owns, not for one they don't", async () => {
    const onAccept = vi.fn()
    const onDecline = vi.fn()
    renderCard({ onAccept, onDecline })

    // Only donor-a is owned by "doctor-a" (currentDoctorId).
    const acceptButtons = screen.getAllByRole("button", { name: "Accept" })
    expect(acceptButtons).toHaveLength(1)

    await userEvent.click(acceptButtons[0])
    expect(onAccept).toHaveBeenCalledWith(
      expect.objectContaining({ id: "pair-a", donor_id: "donor-a" })
    )
  })

  it("does not show decision actions once the proposal is no longer proposed", () => {
    renderCard({
      proposal: makeProposal({ status: "accepted" }),
      onAccept: vi.fn(),
      onDecline: vi.fn(),
    })

    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument()
  })

  it("shows Cancel proposal only when onCancel is provided", () => {
    const { rerender } = render(
      <MemoryRouter>
        <ExchangeProposalCard proposal={makeProposal()} currentDoctorId="doctor-a" />
      </MemoryRouter>
    )
    expect(screen.queryByRole("button", { name: "Cancel proposal" })).not.toBeInTheDocument()

    rerender(
      <MemoryRouter>
        <ExchangeProposalCard
          proposal={makeProposal()}
          currentDoctorId="doctor-a"
          onCancel={vi.fn()}
        />
      </MemoryRouter>
    )
    expect(screen.getByRole("button", { name: "Cancel proposal" })).toBeInTheDocument()
  })

  it("uses only workflow (neutral) badge styling for status, never the clinical palette", () => {
    // K10 safety rule: proposal workflow state must never share a color
    // token with clinical status (DSA/mismatch severity elsewhere on this
    // page) -- see index.css's @theme comment.
    renderCard()

    const statusBadge = screen.getByText("Pending")
    const decisionBadges = screen.getAllByText("Awaiting decision")

    for (const badge of [statusBadge, ...decisionBadges]) {
      const classList = badge.closest("span").className
      expect(classList).not.toMatch(/\bbg-clear\b|\btext-clear\b/)
      expect(classList).not.toMatch(/\bbg-moderate\b|\btext-moderate\b/)
      expect(classList).not.toMatch(/\bbg-high-moderate\b|\btext-high-moderate\b/)
      expect(classList).not.toMatch(/\bbg-high-risk\b|\btext-high-risk\b/)
    }
  })
})

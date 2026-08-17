// src/pages/ExchangePoolPage.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { getExchangeCompare, getExchangeHardToMatch, getExchangeMatch } from "../api/exchange"
import { createExchangeProposal } from "../api/exchangeProposals"
import ExchangePoolPage from "./ExchangePoolPage"

vi.mock("../api/exchange", () => ({
  getExchangeMatch: vi.fn(),
  getExchangeCompare: vi.fn(),
  getExchangeHardToMatch: vi.fn(),
}))
vi.mock("../api/exchangeProposals", () => ({ createExchangeProposal: vi.fn() }))

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
    {
      from_pair_id: "donor-a",
      to_pair_id: "donor-b",
      mismatch_result: { total_mismatches: 1 },
      dsa_result: {},
    },
    {
      from_pair_id: "donor-b",
      to_pair_id: "donor-a",
      mismatch_result: { total_mismatches: 0 },
      dsa_result: {},
    },
  ],
  selected_cycles: [{ pair_ids: ["donor-a", "donor-b"], weight: 2 }],
  explanations: [],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/exchange"]}>
      <Routes>
        <Route path="/exchange" element={<ExchangePoolPage />} />
        <Route path="/exchange/proposals" element={<div>Proposals inbox</div>} />
        <Route
          path="/exchange/proposals/:proposalId"
          element={<div>Proposal detail page</div>}
        />
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
    expect(screen.getByText("Cycle #1")).toBeInTheDocument()
  })

  it("renders the cycle as a card with the full chain, at every breakpoint", async () => {
    // K10: cards are the primary (and only) representation of a cycle, no
    // separate table -- and they render unconditionally, not inside any
    // `hidden` wrapper, so they're visible at every breakpoint.
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)

    renderPage()

    expect(await screen.findByText("Cycle #1")).toBeInTheDocument()
    expect(screen.getByText("2 pairs · weight 2.0")).toBeInTheDocument()
    // Both hops in the 2-cycle show their mismatch count.
    expect(screen.getByText("1 mismatch")).toBeInTheDocument()
    expect(screen.getByText("0 mismatches")).toBeInTheDocument()
    expect(screen.getByText("↺ closes back to the first pair")).toBeInTheDocument()
  })

  it("keeps the graph a desktop-only affordance behind `hidden md:block`", async () => {
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)

    renderPage()

    await screen.findByText("Cycle #1")
    const graph = screen.getByRole("img", { name: "Paired exchange candidate graph" })
    expect(graph.closest(".hidden.md\\:block")).not.toBeNull()
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

  it("switches to the cross-policy comparison view and shows which policies agree on each cycle", async () => {
    // K8: a cycle every policy selects is robust; one only a single policy
    // picks is a policy artefact -- the comparison view is meant to make
    // that visible instead of asking the coordinator to pick a policy blind.
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)
    getExchangeCompare.mockResolvedValue({
      policies: ["max_transplants", "max_quality", "equity_weighted", "max_lkdpi_quality"],
      nodes: [NODE_A, NODE_B],
      edges: MATCH_RESPONSE.edges,
      cycles: [
        {
          pair_ids: ["donor-a", "donor-b"],
          weight_by_policy: { max_transplants: 2, max_quality: 2 },
          selected_by: ["max_transplants", "max_quality"],
        },
      ],
    })

    const user = userEvent.setup()
    renderPage()
    await screen.findByText("Incompatible pairs")

    await user.click(screen.getByRole("radio", { name: "Compare" }))

    expect(await screen.findByText("Candidate cycle · 2 pairs")).toBeInTheDocument()
    expect(screen.getByText("Selected by 2 of 4 policies")).toBeInTheDocument()
    expect(screen.getByText("Max transplants")).toBeInTheDocument()
    expect(screen.getByText("Max quality")).toBeInTheDocument()
    // Not selected by these two, so they shouldn't render as badges here.
    expect(screen.queryByText("Equity-weighted")).not.toBeInTheDocument()
    expect(screen.queryByText("Max donor quality (LKDPI)")).not.toBeInTheDocument()
  })

  it("shows an empty-state message in the comparison view when no policy selects anything", async () => {
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)
    getExchangeCompare.mockResolvedValue({
      policies: ["max_transplants", "max_quality", "equity_weighted", "max_lkdpi_quality"],
      nodes: [],
      edges: [],
      cycles: [],
    })

    const user = userEvent.setup()
    renderPage()
    await screen.findByText("Incompatible pairs")

    await user.click(screen.getByRole("radio", { name: "Compare" }))

    expect(
      await screen.findByText("No policy selects any cycle in the pool right now.")
    ).toBeInTheDocument()
  })

  it("switches to the hard-to-match worklist and shows verdict + wait time per pair", async () => {
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)
    getExchangeHardToMatch.mockResolvedValue({
      pairs: [
        {
          node: { ...NODE_A, pair_id: "donor-isolated" },
          cpra_percentage: 42.5,
          wait_days: 900,
          verdict: "no_donor_in",
          outbound_blocked: {},
          inbound_blocked: { abo: 3 },
          candidate_cycles: 0,
        },
      ],
    })

    const user = userEvent.setup()
    renderPage()
    await screen.findByText("Incompatible pairs")

    await user.click(screen.getByRole("radio", { name: "Hard to match" }))

    expect(await screen.findByText("No compatible donor")).toBeInTheDocument()
    expect(screen.getByText(/waiting 900d/)).toBeInTheDocument()
    expect(screen.getByText(/cPRA 42.5%/)).toBeInTheDocument()
  })

  it("shows an empty-state message in the hard-to-match view when every pair is matched somewhere", async () => {
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)
    getExchangeHardToMatch.mockResolvedValue({ pairs: [] })

    const user = userEvent.setup()
    renderPage()
    await screen.findByText("Incompatible pairs")

    await user.click(screen.getByRole("radio", { name: "Hard to match" }))

    expect(
      await screen.findByText("Every pool pair is matched by at least one policy right now.")
    ).toBeInTheDocument()
  })

  it("proposes the cycle and navigates to its detail page on success", async () => {
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)
    createExchangeProposal.mockResolvedValue({ id: "proposal-1" })

    const user = userEvent.setup()
    renderPage()
    await screen.findByText("Cycle #1")

    await user.click(screen.getByRole("button", { name: "Propose this cycle" }))

    expect(createExchangeProposal).toHaveBeenCalledWith("max_transplants", ["donor-a", "donor-b"])
    expect(await screen.findByText("Proposal detail page")).toBeInTheDocument()
  })

  it("shows an error and stays on the pool page when proposing fails", async () => {
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)
    createExchangeProposal.mockRejectedValue(new Error("Donor already committed elsewhere"))

    const user = userEvent.setup()
    renderPage()
    await screen.findByText("Cycle #1")

    await user.click(screen.getByRole("button", { name: "Propose this cycle" }))

    expect(await screen.findByText("Donor already committed elsewhere")).toBeInTheDocument()
    expect(screen.getByText("Cycle #1")).toBeInTheDocument()
  })

  it("links to the proposals inbox", async () => {
    getExchangeMatch.mockResolvedValue(MATCH_RESPONSE)

    renderPage()

    expect(await screen.findByRole("link", { name: /view proposals/i })).toHaveAttribute(
      "href",
      "/exchange/proposals"
    )
  })
})

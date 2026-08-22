// src/components/domain/ExchangeCycleGraph.test.jsx
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import ExchangeCycleGraph from "./ExchangeCycleGraph"

function makeNode(pairId, overrides = {}) {
  return {
    pair_id: pairId,
    patient_blood_type: "O",
    donor_blood_type: "A",
    patient_hospital_name: "H",
    patient_doctor_full_name: "Dr",
    donor_hospital_name: "H",
    donor_doctor_full_name: "Dr",
    ...overrides,
  }
}

describe("ExchangeCycleGraph — DSA review indication (review #2 bug 13)", () => {
  it("renders an edge needing desensitisation review with a dashed, review-colored stroke and a tooltip", () => {
    const a = makeNode("a")
    const b = makeNode("b")
    const edge = {
      from_pair_id: "a",
      to_pair_id: "b",
      mismatch_result: { total_mismatches: 2 },
      dsa_result: { requires_review: true, is_halted: false },
    }

    const { container } = render(
      <ExchangeCycleGraph nodes={[a, b]} edges={[edge]} selectedCycles={[]} />
    )

    const line = container.querySelector("line")
    expect(line).not.toBeNull()
    expect(line.getAttribute("stroke-dasharray")).toBe("4 3")
    expect(line.querySelector("title").textContent).toMatch(/requires desensitisation/)
  })

  it("renders an ordinary edge with no dash when review isn't needed", () => {
    const a = makeNode("a")
    const b = makeNode("b")
    const edge = {
      from_pair_id: "a",
      to_pair_id: "b",
      mismatch_result: { total_mismatches: 0 },
      dsa_result: { requires_review: false, is_halted: false },
    }

    const { container } = render(
      <ExchangeCycleGraph nodes={[a, b]} edges={[edge]} selectedCycles={[]} />
    )

    const line = container.querySelector("line")
    expect(line.getAttribute("stroke-dasharray")).toBeNull()
    expect(line.querySelector("title").textContent).toMatch(/no review needed/)
  })

  it("shows the legend entry for the review indicator", () => {
    const a = makeNode("a")
    const b = makeNode("b")
    const { getByText } = render(
      <ExchangeCycleGraph nodes={[a, b]} edges={[]} selectedCycles={[]} />
    )
    expect(getByText(/Needs desensitisation review/)).toBeInTheDocument()
  })
})

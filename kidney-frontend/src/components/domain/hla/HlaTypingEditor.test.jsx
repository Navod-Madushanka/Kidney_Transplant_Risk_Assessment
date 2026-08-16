// src/components/domain/hla/HlaTypingEditor.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import HlaTypingEditor from "./HlaTypingEditor"

const SAVED_ENTRIES = [
  { locus: "A", allele_1: "29", allele_2: "33" },
  { locus: "B", allele_1: "07", allele_2: "58" },
]

describe("HlaTypingEditor", () => {
  // Regression test: the patient/donor detail pages mount this editor while
  // their fetch is still in flight (loadState="loading", initialEntries=[]),
  // then flip to "loaded" with the real rows once it resolves. rows used to
  // be seeded from initialEntries only inside useState's lazy initializer,
  // which React never re-runs -- so saved HLA typing silently never
  // appeared, even though the data was fetched correctly.
  it("populates rows once the async load finishes, not just at mount", () => {
    const { rerender } = render(
      <HlaTypingEditor loadState="loading" initialEntries={[]} onSave={vi.fn()} />
    )

    rerender(
      <HlaTypingEditor loadState="loaded" initialEntries={SAVED_ENTRIES} onSave={vi.fn()} />
    )

    expect(screen.getAllByPlaceholderText("Allele 1").map((el) => el.value)).toEqual([
      "29",
      "07",
    ])
    expect(screen.getAllByPlaceholderText("Allele 2").map((el) => el.value)).toEqual([
      "33",
      "58",
    ])
  })

  it("does not clobber an in-progress edit on an unrelated re-render", async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <HlaTypingEditor loadState="loaded" initialEntries={SAVED_ENTRIES} onSave={vi.fn()} />
    )

    const firstAllele1 = screen.getAllByPlaceholderText("Allele 1")[0]
    await user.clear(firstAllele1)
    await user.type(firstAllele1, "68")

    // Same loadState, same initialEntries reference -- simulates the parent
    // re-rendering for an unrelated reason (e.g. opening a modal).
    rerender(
      <HlaTypingEditor loadState="loaded" initialEntries={SAVED_ENTRIES} onSave={vi.fn()} />
    )

    expect(screen.getAllByPlaceholderText("Allele 1")[0].value).toBe("68")
  })
})

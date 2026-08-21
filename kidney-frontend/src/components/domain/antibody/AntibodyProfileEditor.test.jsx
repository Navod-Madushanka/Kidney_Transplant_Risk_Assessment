// src/components/domain/antibody/AntibodyProfileEditor.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import AntibodyProfileEditor from "./AntibodyProfileEditor"

const SAVED_ENTRIES = [
  { antigen: "DP1", mfi: 457.08 },
  { antigen: "DQ4", mfi: 179.54 },
]

describe("AntibodyProfileEditor", () => {
  // Regression test: see HlaTypingEditor.test.jsx's matching case -- same
  // bug, same shared root cause (rows only ever seeded from initialEntries
  // inside useState's lazy initializer, which doesn't re-run once the
  // parent's async fetch resolves after this component has already
  // mounted).
  it("populates rows once the async load finishes, not just at mount", () => {
    const { rerender } = render(
      <AntibodyProfileEditor loadState="loading" initialEntries={[]} onSave={vi.fn()} />
    )

    rerender(
      <AntibodyProfileEditor loadState="loaded" initialEntries={SAVED_ENTRIES} onSave={vi.fn()} />
    )

    expect(screen.getAllByPlaceholderText("Antigen (e.g. DQ7)").map((el) => el.value)).toEqual([
      "DP1",
      "DQ4",
    ])
    expect(screen.getAllByPlaceholderText("MFI value").map((el) => el.value)).toEqual([
      "457.08",
      "179.54",
    ])
  })

  it("does not clobber an in-progress edit on an unrelated re-render", async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <AntibodyProfileEditor loadState="loaded" initialEntries={SAVED_ENTRIES} onSave={vi.fn()} />
    )

    const firstAntigen = screen.getAllByPlaceholderText("Antigen (e.g. DQ7)")[0]
    await user.clear(firstAntigen)
    await user.type(firstAntigen, "DQ9")

    rerender(
      <AntibodyProfileEditor loadState="loaded" initialEntries={SAVED_ENTRIES} onSave={vi.fn()} />
    )

    expect(screen.getAllByPlaceholderText("Antigen (e.g. DQ7)")[0].value).toBe("DQ9")
  })

  it("rejects an allele-level antigen (e.g. \"B*44:02\") instead of silently saving it", async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<AntibodyProfileEditor loadState="loaded" initialEntries={[]} onSave={onSave} />)

    await user.type(screen.getAllByPlaceholderText("Antigen (e.g. DQ7)")[0], "B*44:02")
    await user.type(screen.getAllByPlaceholderText("MFI value")[0], "12000")
    await user.click(screen.getByRole("button", { name: /save antibody profile/i }))

    expect(
      await screen.findByText(/serological designation.*B44.*allele-level typing.*B\*44:02/)
    ).toBeInTheDocument()
    expect(onSave).not.toHaveBeenCalled()
  })
})

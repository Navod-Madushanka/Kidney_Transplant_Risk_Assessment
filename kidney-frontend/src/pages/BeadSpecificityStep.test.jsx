// src/pages/BeadSpecificityStep.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { WizardContext } from "../context/WizardContext"
import BeadSpecificityStep from "./BeadSpecificityStep"

function renderStep(wizardValue) {
  return render(
    <WizardContext.Provider value={wizardValue}>
      <MemoryRouter initialEntries={["/checks/new/bead-chart"]}>
        <Routes>
          <Route path="/checks/new/bead-chart" element={<BeadSpecificityStep />} />
          <Route path="/checks/new/review" element={<div>Review Step</div>} />
          <Route path="/checks/new/sensitization" element={<div>Sensitization Step</div>} />
        </Routes>
      </MemoryRouter>
    </WizardContext.Provider>
  )
}

function makeWizardValue(overrides = {}) {
  return {
    state: { bead_specificity: [] },
    actions: { setBeadSpecificity: vi.fn(), unlockStep: vi.fn(), setOcrVerified: vi.fn(), ...overrides },
  }
}

function makeOcrExtractedWizardValue(ocrVerified = false) {
  return {
    state: {
      bead_specificity: [{ antigen: "DQ7", mfi: 1200 }],
      extraction: { documents: { bead_specificity_page_1: { status: "done" } } },
      ocr_verified: { hla_typing: false, bead_specificity: ocrVerified },
    },
    actions: { setBeadSpecificity: vi.fn(), unlockStep: vi.fn(), setOcrVerified: vi.fn() },
  }
}

describe("BeadSpecificityStep", () => {
  it("continuing with every row blank submits an empty list and advances", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue()
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(wizardValue.actions.setBeadSpecificity).toHaveBeenCalledWith([])
    expect(wizardValue.actions.unlockStep).toHaveBeenCalledWith(5)
    expect(await screen.findByText("Review Step")).toBeInTheDocument()
  })

  it("requires an MFI value once an antigen has been entered", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue()
    renderStep(wizardValue)

    await user.type(screen.getAllByPlaceholderText("Antigen (e.g. B*44:02)")[0], "DQ7")
    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText("MFI is required")).toBeInTheDocument()
    expect(wizardValue.actions.setBeadSpecificity).not.toHaveBeenCalled()
  })

  it("rejects a non-numeric MFI value", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue()
    renderStep(wizardValue)

    await user.type(screen.getAllByPlaceholderText("Antigen (e.g. B*44:02)")[0], "DQ7")
    await user.type(screen.getAllByPlaceholderText("MFI value")[0], "not-a-number")
    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText("MFI must be a number")).toBeInTheDocument()
    expect(wizardValue.actions.setBeadSpecificity).not.toHaveBeenCalled()
  })

  it("submits a fully-filled row as a numeric MFI and advances to review", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue()
    renderStep(wizardValue)

    await user.type(screen.getAllByPlaceholderText("Antigen (e.g. B*44:02)")[0], "DQ7")
    await user.type(screen.getAllByPlaceholderText("MFI value")[0], "3500")
    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(wizardValue.actions.setBeadSpecificity).toHaveBeenCalledWith([
      { antigen: "DQ7", mfi: 3500 },
    ])
    expect(wizardValue.actions.unlockStep).toHaveBeenCalledWith(5)
    expect(await screen.findByText("Review Step")).toBeInTheDocument()
  })

  it("filters rows by antigen and by MFI search independently", async () => {
    const user = userEvent.setup()
    const wizardValue = {
      state: {
        bead_specificity: [
          { antigen: "B*44:02", mfi: 3500 },
          { antigen: "DQ7", mfi: 1200 },
        ],
      },
      actions: { setBeadSpecificity: vi.fn(), unlockStep: vi.fn() },
    }
    renderStep(wizardValue)

    expect(screen.getAllByPlaceholderText("Antigen (e.g. B*44:02)")).toHaveLength(3) // 2 rows + trailing blank

    await user.type(screen.getByLabelText("Search by antigen/bead name"), "DQ7")
    const antigenInputs = screen.getAllByPlaceholderText("Antigen (e.g. B*44:02)")
    expect(antigenInputs).toHaveLength(1)
    expect(antigenInputs[0]).toHaveValue("DQ7")

    await user.clear(screen.getByLabelText("Search by antigen/bead name"))
    await user.type(screen.getByLabelText("Search by MFI value"), "3500")
    const antigenInputsAfterMfiSearch = screen.getAllByPlaceholderText("Antigen (e.g. B*44:02)")
    expect(antigenInputsAfterMfiSearch).toHaveLength(1)
    expect(antigenInputsAfterMfiSearch[0]).toHaveValue("B*44:02")
  })

  it("shows a no-match message and clears the search if Continue finds a row error hidden behind it", async () => {
    const user = userEvent.setup()
    const wizardValue = {
      state: { bead_specificity: [{ antigen: "DQ7", mfi: 1200 }] },
      actions: { setBeadSpecificity: vi.fn(), unlockStep: vi.fn() },
    }
    renderStep(wizardValue)

    await user.type(screen.getAllByPlaceholderText("MFI value")[0], "not-a-number")
    await user.type(screen.getByLabelText("Search by antigen/bead name"), "no-such-antigen")
    expect(screen.getByText("No rows match your search.")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText("MFI must be a number")).toBeInTheDocument()
    expect(screen.getByLabelText("Search by antigen/bead name")).toHaveValue("")
  })

  it("doesn't show a review confirmation when nothing was OCR-extracted", () => {
    renderStep(makeWizardValue())

    expect(
      screen.queryByText("I have reviewed this bead specificity chart against the source document")
    ).not.toBeInTheDocument()
  })

  it("blocks Continue until the OCR review is confirmed", async () => {
    const user = userEvent.setup()
    const wizardValue = makeOcrExtractedWizardValue(false)
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(
      await screen.findByText(/refuses to run on\s*unverified OCR data/)
    ).toBeInTheDocument()
    expect(wizardValue.actions.setBeadSpecificity).not.toHaveBeenCalled()
  })

  it("lets Continue through once the OCR review is confirmed", async () => {
    const user = userEvent.setup()
    const wizardValue = makeOcrExtractedWizardValue(true)
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(wizardValue.actions.setBeadSpecificity).toHaveBeenCalledWith([
      { antigen: "DQ7", mfi: 1200 },
    ])
    expect(await screen.findByText("Review Step")).toBeInTheDocument()
  })

  it("toggling the review confirmation dispatches setOcrVerified", async () => {
    const user = userEvent.setup()
    const wizardValue = makeOcrExtractedWizardValue(false)
    renderStep(wizardValue)

    await user.click(
      screen.getByRole("switch", {
        name: /I have reviewed this bead specificity chart against the source document/,
      })
    )

    expect(wizardValue.actions.setOcrVerified).toHaveBeenCalledWith("bead_specificity", true)
  })

  it("navigates back to the sensitization step without validating", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue()
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /back/i }))

    expect(await screen.findByText("Sensitization Step")).toBeInTheDocument()
    expect(wizardValue.actions.setBeadSpecificity).not.toHaveBeenCalled()
  })
})

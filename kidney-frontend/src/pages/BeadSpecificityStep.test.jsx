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
    actions: { setBeadSpecificity: vi.fn(), unlockStep: vi.fn(), ...overrides },
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

  it("navigates back to the sensitization step without validating", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue()
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /back/i }))

    expect(await screen.findByText("Sensitization Step")).toBeInTheDocument()
    expect(wizardValue.actions.setBeadSpecificity).not.toHaveBeenCalled()
  })
})

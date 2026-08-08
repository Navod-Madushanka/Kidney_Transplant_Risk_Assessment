// src/pages/HlaTypingStep.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { WizardContext } from "../context/WizardContext"
import { HLA_LOCUS_OPTIONS } from "../constants/clinicalEnums"
import HlaTypingStep from "./HlaTypingStep"

function renderStep(wizardValue) {
  return render(
    <WizardContext.Provider value={wizardValue}>
      <MemoryRouter initialEntries={["/checks/new/hla"]}>
        <Routes>
          <Route path="/checks/new/hla" element={<HlaTypingStep />} />
          <Route path="/checks/new/details" element={<div>Details Step</div>} />
          <Route path="/checks/new/sensitization" element={<div>Sensitization Step</div>} />
        </Routes>
      </MemoryRouter>
    </WizardContext.Provider>
  )
}

// One filled-in row per locus so allele validation never blocks these
// tests — they're isolated to the OCR-verification gate, not re-testing
// the pre-existing allele-required validation.
function fullHlaRows() {
  return HLA_LOCUS_OPTIONS.map((option) => ({ locus: option.value, allele_1: "01", allele_2: "02" }))
}

function makeWizardValue({ extraction, ocrVerified } = {}) {
  return {
    state: {
      patient_hla: fullHlaRows(),
      donor_hla: fullHlaRows(),
      extraction: extraction ?? { documents: {} },
      ocr_verified: { hla_typing: ocrVerified ?? false, bead_specificity: false },
    },
    actions: {
      setPatientHlaRow: vi.fn(),
      setDonorHlaRow: vi.fn(),
      setOcrVerified: vi.fn(),
      unlockStep: vi.fn(),
    },
  }
}

describe("HlaTypingStep — OCR verification gate", () => {
  it("doesn't show a review confirmation when nothing was OCR-extracted", () => {
    renderStep(makeWizardValue())

    expect(
      screen.queryByText("I have reviewed this HLA typing against the source document")
    ).not.toBeInTheDocument()
  })

  it("advances straight through when nothing was OCR-extracted", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue()
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText("Sensitization Step")).toBeInTheDocument()
  })

  it("blocks Continue until the OCR review is confirmed", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue({
      extraction: { documents: { hla_typing_report: { status: "done" } } },
      ocrVerified: false,
    })
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(
      await screen.findByText(/refuses to run on\s*unverified OCR data/)
    ).toBeInTheDocument()
    expect(wizardValue.actions.unlockStep).not.toHaveBeenCalled()
  })

  it("lets Continue through once the OCR review is confirmed", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue({
      extraction: { documents: { hla_typing_report: { status: "done" } } },
      ocrVerified: true,
    })
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText("Sensitization Step")).toBeInTheDocument()
  })

  it("toggling the review confirmation dispatches setOcrVerified", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue({
      extraction: { documents: { hla_typing_report: { status: "done" } } },
      ocrVerified: false,
    })
    renderStep(wizardValue)

    await user.click(
      screen.getByRole("switch", {
        name: /I have reviewed this HLA typing against the source document/,
      })
    )

    expect(wizardValue.actions.setOcrVerified).toHaveBeenCalledWith("hla_typing", true)
  })
})

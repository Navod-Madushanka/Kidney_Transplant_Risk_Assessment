// src/pages/DetailsStep.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { WizardContext } from "../context/WizardContext"
import DetailsStep from "./DetailsStep"

function renderStep(wizardValue) {
  return render(
    <WizardContext.Provider value={wizardValue}>
      <MemoryRouter initialEntries={["/checks/new/details"]}>
        <Routes>
          <Route path="/checks/new/details" element={<DetailsStep />} />
          <Route path="/checks/new/photos" element={<div>Photos Step</div>} />
          <Route path="/checks/new/hla" element={<div>HLA Step</div>} />
        </Routes>
      </MemoryRouter>
    </WizardContext.Provider>
  )
}

function fullPersonDetails() {
  return {
    full_name: "Test Person",
    date_of_birth: "1990-01-01",
    blood_type: "O",
    rh_factor: "+",
    nic_number: "",
  }
}

function makeWizardValue({ extraction, ocrVerified } = {}) {
  return {
    state: {
      patient_details: fullPersonDetails(),
      donor_details: fullPersonDetails(),
      extraction: extraction ?? { documents: {} },
      ocr_verified: { details: ocrVerified ?? false, hla_typing: false, bead_specificity: false },
    },
    actions: {
      setPatientDetails: vi.fn(),
      setDonorDetails: vi.fn(),
      setOcrVerified: vi.fn(),
      unlockStep: vi.fn(),
    },
  }
}

describe("DetailsStep — OCR verification gate", () => {
  it("doesn't show a review confirmation when nothing was OCR-extracted", () => {
    renderStep(makeWizardValue())

    expect(
      screen.queryByText(/I have reviewed these names, dates of birth, and blood groups/)
    ).not.toBeInTheDocument()
  })

  it("advances straight through when nothing was OCR-extracted", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue()
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText("HLA Step")).toBeInTheDocument()
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

    expect(await screen.findByText("HLA Step")).toBeInTheDocument()
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
        name: /I have reviewed these names, dates of birth, and blood groups/,
      })
    )

    expect(wizardValue.actions.setOcrVerified).toHaveBeenCalledWith("details", true)
  })

  it("shows the review confirmation when any document (not just a fixed one) finished OCR", () => {
    renderStep(
      makeWizardValue({
        extraction: { documents: { bead_specificity_page_1: { status: "done" } } },
      })
    )

    expect(
      screen.getByText(/I have reviewed these names, dates of birth, and blood groups/)
    ).toBeInTheDocument()
  })
})

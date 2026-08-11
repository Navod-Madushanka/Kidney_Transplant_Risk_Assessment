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

function makeWizardValue({
  extraction,
  ocrVerified,
  patientDetails,
  donorDetails,
  patientRecord = null,
  donorRecord = null,
} = {}) {
  return {
    state: {
      subject: { patientRecord, donorRecord },
      patient_details: patientDetails ?? fullPersonDetails(),
      donor_details: donorDetails ?? fullPersonDetails(),
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

describe("DetailsStep — E3.6 blood-type conflict against the linked record", () => {
  it("blocks Continue when the document's blood type disagrees with the linked patient record", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue({
      patientDetails: { ...fullPersonDetails(), blood_type: "B", rh_factor: "+" },
      patientRecord: { blood_type: "A", rh_factor: "+" },
    })
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText(/reads blood group B\+/)).toBeInTheDocument()
    expect(screen.getByText(/record\s*says A\+/)).toBeInTheDocument()
    expect(wizardValue.actions.unlockStep).not.toHaveBeenCalled()
  })

  it("blocks Continue when the donor's rh factor disagrees with the linked donor record", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue({
      donorDetails: { ...fullPersonDetails(), blood_type: "O", rh_factor: "+" },
      donorRecord: { blood_type: "O", rh_factor: "-" },
    })
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText(/reads blood group O\+/)).toBeInTheDocument()
    expect(wizardValue.actions.unlockStep).not.toHaveBeenCalled()
  })

  it("allows Continue when details match the linked record", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue({
      patientDetails: { ...fullPersonDetails(), blood_type: "O", rh_factor: "+" },
      patientRecord: { blood_type: "O", rh_factor: "+" },
      donorDetails: { ...fullPersonDetails(), blood_type: "A", rh_factor: "-" },
      donorRecord: { blood_type: "A", rh_factor: "-" },
    })
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText("HLA Step")).toBeInTheDocument()
  })

  it("has nothing to compare against when there's no linked record yet", async () => {
    const user = userEvent.setup()
    const wizardValue = makeWizardValue({ patientRecord: null, donorRecord: null })
    renderStep(wizardValue)

    await user.click(screen.getByRole("button", { name: /continue/i }))

    expect(await screen.findByText("HLA Step")).toBeInTheDocument()
  })
})

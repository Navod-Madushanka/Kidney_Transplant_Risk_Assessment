// src/pages/SubjectStep.test.jsx
import { useState } from "react"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { WizardContext } from "../context/WizardContext"
import SubjectStep from "./SubjectStep"
import { listPatients, getPatient } from "../api/patients"
import { listDonors, getDonor } from "../api/donors"
import { getCompatibilityReadiness } from "../api/compatibility"
import { createPair } from "../api/pairs"

vi.mock("../api/patients", () => ({
  listPatients: vi.fn(),
  getPatient: vi.fn(),
}))
vi.mock("../api/donors", () => ({
  listDonors: vi.fn(),
  getDonor: vi.fn(),
}))
vi.mock("../api/compatibility", () => ({
  getCompatibilityReadiness: vi.fn(),
}))
vi.mock("../api/pairs", () => ({ createPair: vi.fn() }))

const PATIENT_RECORD = {
  id: "patient-1",
  full_name: "Alice",
  nic_number: "1",
  date_of_birth: "1990-01-01",
  blood_type: "O",
  rh_factor: "+",
}
const DONOR_RECORD = {
  id: "donor-1",
  full_name: "Bob",
  nic_number: "2",
  date_of_birth: "1985-01-01",
  blood_type: "O",
  rh_factor: "+",
}

const EMPTY_DETAILS = { full_name: "", nic_number: "", date_of_birth: "", blood_type: "", rh_factor: "" }

// Actions like setReadiness/setLinkedRecords/setPatientDetails only matter
// to SubjectStep if they actually feed back into re-rendered context state
// -- a bare vi.fn() mock (as DetailsStep.test.jsx's static wizardValue
// uses) never does that, which is exactly what SubjectStep needs: it reads
// readiness/patient_details/donor_details back off wizard context state,
// not local state. This small stateful harness mimics WizardProvider's
// real reducer wiring just enough for that round trip to work in a test.
function StatefulWizard({ initialSubject, initialPatientDetails, initialDonorDetails, children }) {
  const [subject, setSubject] = useState(initialSubject)
  const [patientDetails, setPatientDetailsState] = useState(initialPatientDetails || EMPTY_DETAILS)
  const [donorDetails, setDonorDetailsState] = useState(initialDonorDetails || EMPTY_DETAILS)

  const value = {
    state: { subject, patient_details: patientDetails, donor_details: donorDetails },
    actions: {
      setSubject: (patch) => setSubject((prev) => ({ ...prev, ...patch })),
      setReadiness: (readiness) => setSubject((prev) => ({ ...prev, readiness })),
      setLinkedRecords: (patientRecord, donorRecord) =>
        setSubject((prev) => ({ ...prev, patientRecord, donorRecord })),
      setPatientDetails: (patch) => setPatientDetailsState((prev) => ({ ...prev, ...patch })),
      setDonorDetails: (patch) => setDonorDetailsState((prev) => ({ ...prev, ...patch })),
      unlockStep: vi.fn(),
    },
  }

  return <WizardContext.Provider value={value}>{children}</WizardContext.Provider>
}

function renderStep({
  patientId = "patient-1",
  donorId = "donor-1",
  patientDetails,
  donorDetails,
} = {}) {
  return render(
    <StatefulWizard
      initialSubject={{
        mode: "select",
        patientId,
        donorId,
        patientRecord: null,
        donorRecord: null,
        readiness: null,
      }}
      initialPatientDetails={patientDetails}
      initialDonorDetails={donorDetails}
    >
      <MemoryRouter initialEntries={["/checks/new/subject"]}>
        <Routes>
          <Route path="/checks/new/subject" element={<SubjectStep />} />
          <Route path="/checks/new/photos" element={<div>Photos Step</div>} />
          <Route path="/checks/new/details" element={<div>Details Step</div>} />
        </Routes>
      </MemoryRouter>
    </StatefulWizard>
  )
}

describe("SubjectStep — readiness panel", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listPatients.mockResolvedValue([PATIENT_RECORD])
    listDonors.mockResolvedValue([DONOR_RECORD])
    getPatient.mockResolvedValue(PATIENT_RECORD)
    getDonor.mockResolvedValue(DONOR_RECORD)
  })

  it("disables Continue when there's a blocking gap", async () => {
    getCompatibilityReadiness.mockResolvedValue({
      can_run: false,
      blocking: [{ code: "missing_hla_patient_A", label: "patient A typing", subject: "patient" }],
      lkdpi_gaps: [],
      donor_risk_projection_gaps: [],
      donor_risk_contraindication_gaps: [],
    })

    renderStep()

    expect(await screen.findByText("patient A typing")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled()
  })

  it("keeps Continue enabled when only a score gap is present", async () => {
    getCompatibilityReadiness.mockResolvedValue({
      can_run: true,
      blocking: [],
      lkdpi_gaps: [{ code: "lkdpi_donor_weight", label: "donor weight", subject: "donor" }],
      donor_risk_projection_gaps: [],
      donor_risk_contraindication_gaps: [],
    })

    renderStep()

    expect(await screen.findByText("donor weight")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /continue/i })).not.toBeDisabled()
  })

  it("shows the all-clear message and no gap panels when nothing is missing", async () => {
    getCompatibilityReadiness.mockResolvedValue({
      can_run: true,
      blocking: [],
      lkdpi_gaps: [],
      donor_risk_projection_gaps: [],
      donor_risk_contraindication_gaps: [],
    })

    renderStep()

    expect(await screen.findByText(/Ready to check/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /continue/i })).not.toBeDisabled()
  })

  it("does not fetch readiness until both a patient and donor are selected", () => {
    renderStep({ patientId: null, donorId: null })

    expect(getCompatibilityReadiness).not.toHaveBeenCalled()
  })

  it("Continue advances to Details (photos now runs before this step)", async () => {
    const user = userEvent.setup()
    getCompatibilityReadiness.mockResolvedValue({
      can_run: true,
      blocking: [],
      lkdpi_gaps: [],
      donor_risk_projection_gaps: [],
      donor_risk_contraindication_gaps: [],
    })

    renderStep()

    const continueButton = await screen.findByRole("button", { name: /continue/i })
    await user.click(continueButton)

    expect(await screen.findByText("Details Step")).toBeInTheDocument()
  })

  it("Back returns to Photos", async () => {
    const user = userEvent.setup()
    getCompatibilityReadiness.mockResolvedValue({
      can_run: true,
      blocking: [],
      lkdpi_gaps: [],
      donor_risk_projection_gaps: [],
      donor_risk_contraindication_gaps: [],
    })

    renderStep()

    await user.click(await screen.findByRole("button", { name: "Back" }))

    expect(await screen.findByText("Photos Step")).toBeInTheDocument()
  })
})

async function fillRequiredFields(user, sectionHeading, { bloodType, rh }) {
  const section = screen.getByRole("heading", { name: sectionHeading }).closest("div")
  await user.type(within(section).getByLabelText("Full name", { exact: false }), `${sectionHeading} Person`)
  await user.type(within(section).getByLabelText("Date of birth", { exact: false }), "1990-01-01")
  await user.click(within(section).getByRole("radio", { name: bloodType }))
  await user.click(within(section).getByRole("radio", { name: rh }))
}

async function saveSection(user, sectionHeading, saveLabel) {
  const section = screen.getByRole("heading", { name: sectionHeading }).closest("div")
  await user.click(within(section).getByRole("button", { name: saveLabel }))
}

async function fillAndSaveBothForms(user) {
  await fillRequiredFields(user, "Patient", { bloodType: "O", rh: "Positive (+)" })
  await saveSection(user, "Patient", "Save patient details")
  await fillRequiredFields(user, "Donor", { bloodType: "O", rh: "Positive (+)" })
  await saveSection(user, "Donor", "Save donor details")
}

// No patient/donor picker exists in this wizard anymore -- reaching this
// step with nothing selected (a plain "New compatibility check", not
// "start from records") means registering a brand-new pair right here.
// See NewCheckFromRecordsPage.jsx for the only remaining "pick an existing
// patient/donor" UI.
describe("SubjectStep — register a new pair", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows the registration form instead of a picker when nothing is selected yet", () => {
    renderStep({ patientId: null, donorId: null })

    expect(screen.getByRole("heading", { name: "Patient" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Donor" })).toBeInTheDocument()
    expect(screen.queryByRole("combobox", { name: /patient/i })).not.toBeInTheDocument()
    expect(screen.queryByRole("combobox", { name: /donor/i })).not.toBeInTheDocument()
  })

  it("pre-fills the forms from documents already extracted on the Photos step", () => {
    renderStep({
      patientId: null,
      donorId: null,
      patientDetails: { ...EMPTY_DETAILS, full_name: "OCR Patient", blood_type: "A", rh_factor: "+" },
      donorDetails: { ...EMPTY_DETAILS, full_name: "OCR Donor", blood_type: "B", rh_factor: "-" },
    })

    expect(screen.getAllByText(/Auto-filled from the documents you uploaded/)).toHaveLength(2)
    expect(screen.getByDisplayValue("OCR Patient")).toBeInTheDocument()
    expect(screen.getByDisplayValue("OCR Donor")).toBeInTheDocument()
  })

  it("Back returns to Photos without registering anything", async () => {
    const user = userEvent.setup()
    renderStep({ patientId: null, donorId: null })

    await user.click(screen.getByRole("button", { name: "Back" }))

    expect(await screen.findByText("Photos Step")).toBeInTheDocument()
    expect(createPair).not.toHaveBeenCalled()
  })

  it("disables Register until both sections are saved", async () => {
    const user = userEvent.setup()
    renderStep({ patientId: null, donorId: null })

    const registerButton = screen.getByRole("button", { name: /register patient/i })
    expect(registerButton).toBeDisabled()

    await fillRequiredFields(user, "Patient", { bloodType: "O", rh: "Positive (+)" })
    await saveSection(user, "Patient", "Save patient details")
    expect(registerButton).toBeDisabled()

    await fillRequiredFields(user, "Donor", { bloodType: "O", rh: "Positive (+)" })
    await saveSection(user, "Donor", "Save donor details")
    expect(registerButton).toBeEnabled()
  })

  it("registers the pair and skips straight to Details, bypassing the readiness/blocking preview", async () => {
    const user = userEvent.setup()
    createPair.mockResolvedValue({
      id: "pair-1",
      patient_id: "new-patient",
      donor_id: "new-donor",
      patient: { ...PATIENT_RECORD, id: "new-patient" },
      donor: { ...DONOR_RECORD, id: "new-donor" },
    })

    renderStep({ patientId: null, donorId: null })

    await fillAndSaveBothForms(user)
    await user.click(screen.getByRole("button", { name: /register patient/i }))

    expect(createPair).toHaveBeenCalledWith({
      patient: expect.objectContaining({ full_name: "Patient Person" }),
      donor: expect.objectContaining({ full_name: "Donor Person" }),
    })
    // A pair registered right here is brand new -- it will always be
    // missing HLA typing (HlaTypingStep, a few steps ahead, is where that
    // gets entered), so the readiness preview built for re-used *existing*
    // records would always show a false-alarm blocking gap here. Skipped
    // entirely rather than dead-ending the doctor on Continue.
    expect(await screen.findByText("Details Step")).toBeInTheDocument()
    expect(getCompatibilityReadiness).not.toHaveBeenCalled()
  })

  it("shows an error and stays on the form when registration fails", async () => {
    const user = userEvent.setup()
    createPair.mockRejectedValue(new Error("You already have a patient with this NIC number."))

    renderStep({ patientId: null, donorId: null })

    await fillAndSaveBothForms(user)
    await user.click(screen.getByRole("button", { name: /register patient/i }))

    expect(await screen.findByText(/already have a patient with this NIC number/)).toBeInTheDocument()
    expect(getCompatibilityReadiness).not.toHaveBeenCalled()
  })
})

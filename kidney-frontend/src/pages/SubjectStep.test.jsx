// src/pages/SubjectStep.test.jsx
import { useState } from "react"
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { WizardContext } from "../context/WizardContext"
import SubjectStep from "./SubjectStep"
import { listPatients, getPatient } from "../api/patients"
import { listDonors, getDonor } from "../api/donors"
import { getCompatibilityReadiness } from "../api/compatibility"

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

// Actions like setReadiness/setLinkedRecords only matter to SubjectStep if
// they actually feed back into re-rendered context state -- a bare vi.fn()
// mock (as DetailsStep.test.jsx's static wizardValue uses) never does that,
// which is exactly what SubjectStep needs: it reads readiness back off
// wizard context state, not local state. This small stateful harness mimics
// WizardProvider's real reducer wiring just enough for that round trip to
// work in a test.
function StatefulWizard({ initialSubject, children }) {
  const [subject, setSubject] = useState(initialSubject)

  const value = {
    state: { subject },
    actions: {
      setSubject: (patch) => setSubject((prev) => ({ ...prev, ...patch })),
      setReadiness: (readiness) => setSubject((prev) => ({ ...prev, readiness })),
      setLinkedRecords: (patientRecord, donorRecord) =>
        setSubject((prev) => ({ ...prev, patientRecord, donorRecord })),
      setPatientDetails: vi.fn(),
      setDonorDetails: vi.fn(),
      unlockStep: vi.fn(),
    },
  }

  return <WizardContext.Provider value={value}>{children}</WizardContext.Provider>
}

function renderStep({ patientId = "patient-1", donorId = "donor-1" } = {}) {
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
    >
      <MemoryRouter initialEntries={["/checks/new/subject"]}>
        <Routes>
          <Route path="/checks/new/subject" element={<SubjectStep />} />
          <Route path="/checks/new/photos" element={<div>Photos Step</div>} />
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
})

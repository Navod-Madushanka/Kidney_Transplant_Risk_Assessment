// src/api/compatibilityWizard.test.js
import { beforeEach, describe, expect, it, vi } from "vitest"
import { submitCompatibilityCheck } from "./compatibilityWizard"
import { apiPost } from "./client"
import {
  updatePatient,
  replacePatientHlaTypings,
  replacePatientAntibodyProfiles,
  replacePatientSensitizationEvents,
} from "./patients"
import { updateDonor, replaceDonorHlaTypings } from "./donors"

vi.mock("./client", () => ({ apiPost: vi.fn() }))
vi.mock("./patients", () => ({
  updatePatient: vi.fn(),
  replacePatientHlaTypings: vi.fn(),
  replacePatientAntibodyProfiles: vi.fn(),
  replacePatientSensitizationEvents: vi.fn(),
}))
vi.mock("./donors", () => ({
  updateDonor: vi.fn(),
  replaceDonorHlaTypings: vi.fn(),
}))

function baseWizardState(overrides = {}) {
  return {
    subject: {
      patientId: "patient-1",
      donorId: "donor-1",
      patientRecord: { sex: "female", weight_kg: 60 },
      donorRecord: {
        egfr: 95,
        systolic_bp: 118,
        diastolic_bp: 76,
        bmi: 24.5,
        has_diabetes: false,
        sex: "male",
        race: "white",
        smoking_status: "never",
        creatinine: 1.0,
        urine_acr: 10,
        is_on_antihypertensive_medication: false,
        family_history_kidney_disease: false,
        weight_kg: 78,
        is_biologically_related: true,
        intended_recipient_id: null,
      },
    },
    patient_details: { full_name: "Alice", date_of_birth: "1990-01-01", blood_type: "O", rh_factor: "+", nic_number: "" },
    donor_details: { full_name: "Bob", date_of_birth: "1985-01-01", blood_type: "O", rh_factor: "+", nic_number: "" },
    patient_hla: [],
    donor_hla: [],
    bead_specificity: [],
    sensitization: {},
    sensitization_dates: {},
    crossmatch: { is_positive: null },
    extraction: { documents: {} },
    ocr_verified: { hla_typing: false, bead_specificity: false },
    ...overrides,
  }
}

describe("submitCompatibilityCheck — writes to linked records, never creates", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Every mocked call resolves with a minimal shape submitCompatibilityCheck reads from.
    updatePatient.mockResolvedValue({ id: "patient-1" })
    updateDonor.mockResolvedValue({ id: "donor-1" })
    apiPost.mockResolvedValue({ id: "report-1" })
  })

  it("updates the linked patient/donor records instead of creating new ones", async () => {
    await submitCompatibilityCheck(baseWizardState())

    expect(updatePatient).toHaveBeenCalledWith(
      "patient-1",
      expect.objectContaining({ full_name: "Alice", sex: "female", weight_kg: 60 })
    )
    expect(updateDonor).toHaveBeenCalledWith(
      "donor-1",
      expect.objectContaining({ full_name: "Bob", egfr: 95, weight_kg: 78, is_biologically_related: true })
    )
  })

  it("replaces sensitization events rather than appending to them", async () => {
    await submitCompatibilityCheck(baseWizardState())

    expect(replacePatientSensitizationEvents).toHaveBeenCalledWith("patient-1", [])
  })

  it("omits ocr_verified when no document was OCR-extracted", async () => {
    await submitCompatibilityCheck(baseWizardState())

    expect(replacePatientHlaTypings).toHaveBeenCalledWith("patient-1", [], undefined)
    expect(replaceDonorHlaTypings).toHaveBeenCalledWith("donor-1", [], undefined)
    expect(replacePatientAntibodyProfiles).toHaveBeenCalledWith("patient-1", [], undefined)
  })

  it("passes the confirmed true flag to both HLA writes when the HLA report was OCR-extracted", async () => {
    const wizardState = baseWizardState({
      extraction: { documents: { hla_typing_report: { status: "done" } } },
      ocr_verified: { hla_typing: true, bead_specificity: false },
    })

    await submitCompatibilityCheck(wizardState)

    expect(replacePatientHlaTypings).toHaveBeenCalledWith("patient-1", [], true)
    expect(replaceDonorHlaTypings).toHaveBeenCalledWith("donor-1", [], true)
    // Bead specificity wasn't OCR-extracted in this scenario -- must stay
    // undefined (trusted-as-manual), not inherit hla_typing's flag.
    expect(replacePatientAntibodyProfiles).toHaveBeenCalledWith("patient-1", [], undefined)
  })

  it("passes the confirmed flag for bead specificity when either page was OCR-extracted", async () => {
    const wizardState = baseWizardState({
      extraction: { documents: { bead_specificity_page_2: { status: "done" } } },
      ocr_verified: { hla_typing: false, bead_specificity: true },
    })

    await submitCompatibilityCheck(wizardState)

    expect(replacePatientAntibodyProfiles).toHaveBeenCalledWith("patient-1", [], true)
    expect(replacePatientHlaTypings).toHaveBeenCalledWith("patient-1", [], undefined)
  })

  it("resumes from progress without re-running already-completed steps", async () => {
    const progress = { patientDetailsDone: true, donorDetailsDone: true }

    await submitCompatibilityCheck(baseWizardState(), progress)

    expect(updatePatient).not.toHaveBeenCalled()
    expect(updateDonor).not.toHaveBeenCalled()
  })
})

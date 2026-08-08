// src/api/compatibilityWizard.test.js
import { beforeEach, describe, expect, it, vi } from "vitest"
import { submitCompatibilityCheck } from "./compatibilityWizard"
import { apiPost } from "./client"
import {
  createPatient,
  replacePatientHlaTypings,
  replacePatientAntibodyProfiles,
  createSensitizationEvents,
} from "./patients"
import { createDonor, replaceDonorHlaTypings } from "./donors"

vi.mock("./client", () => ({ apiPost: vi.fn() }))
vi.mock("./patients", () => ({
  createPatient: vi.fn(),
  replacePatientHlaTypings: vi.fn(),
  replacePatientAntibodyProfiles: vi.fn(),
  createSensitizationEvents: vi.fn(),
}))
vi.mock("./donors", () => ({
  createDonor: vi.fn(),
  replaceDonorHlaTypings: vi.fn(),
}))

function baseWizardState(overrides = {}) {
  return {
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

describe("submitCompatibilityCheck — ocr_verified wiring", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Every mocked call resolves with a minimal shape submitCompatibilityCheck reads from.
    createPatient.mockResolvedValue({ id: "patient-1" })
    createDonor.mockResolvedValue({ id: "donor-1" })
    apiPost.mockResolvedValue({ id: "report-1" })
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
})

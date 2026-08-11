// src/api/pairRegistration.test.js
import { beforeEach, describe, expect, it, vi } from "vitest"
import { submitPairRegistration } from "./pairRegistration"
import { createPair } from "./pairs"
import { uploadPairReportFile, uploadPatientReportFile } from "./reportFiles"

vi.mock("./pairs", () => ({ createPair: vi.fn() }))
vi.mock("./reportFiles", () => ({
  uploadPairReportFile: vi.fn(),
  uploadPatientReportFile: vi.fn(),
}))

function baseInput(overrides = {}) {
  return {
    patient: { full_name: "Alice", date_of_birth: "1990-01-01", blood_type: "O", rh_factor: "+" },
    donor: { full_name: "Bob", date_of_birth: "1985-01-01", blood_type: "O", rh_factor: "+" },
    patientHla: [],
    donorHla: [],
    crossmatch: null,
    ocrVerified: null,
    files: {
      hlaTypingReport: null,
      crossmatchReport: null,
      beadSpecificityPage1: null,
      beadSpecificityPage2: null,
    },
    ...overrides,
  }
}

describe("submitPairRegistration", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    createPair.mockResolvedValue({ id: "pair-1", patient_id: "patient-1", donor_id: "donor-1" })
    uploadPairReportFile.mockResolvedValue({ id: "file-1" })
    uploadPatientReportFile.mockResolvedValue({ id: "file-2" })
  })

  it("registers the pair with no file uploads when nothing was attached", async () => {
    const result = await submitPairRegistration(baseInput())

    expect(createPair).toHaveBeenCalledWith(
      expect.objectContaining({
        patient: expect.objectContaining({ full_name: "Alice" }),
        donor: expect.objectContaining({ full_name: "Bob" }),
      })
    )
    expect(uploadPairReportFile).not.toHaveBeenCalled()
    expect(uploadPatientReportFile).not.toHaveBeenCalled()
    expect(result).toEqual(
      expect.objectContaining({ pairId: "pair-1", patientId: "patient-1", donorId: "donor-1" })
    )
  })

  it("uploads each attached file to its correct owner", async () => {
    const hlaFile = new File(["x"], "hla.pdf")
    const crossmatchFile = new File(["x"], "crossmatch.pdf")
    const bead1 = new File(["x"], "bead1.pdf")
    const bead2 = new File(["x"], "bead2.pdf")

    await submitPairRegistration(
      baseInput({
        files: {
          hlaTypingReport: hlaFile,
          crossmatchReport: crossmatchFile,
          beadSpecificityPage1: bead1,
          beadSpecificityPage2: bead2,
        },
      })
    )

    expect(uploadPairReportFile).toHaveBeenCalledWith("pair-1", "hla_typing_report", hlaFile)
    expect(uploadPairReportFile).toHaveBeenCalledWith("pair-1", "crossmatch_report", crossmatchFile)
    expect(uploadPatientReportFile).toHaveBeenCalledWith(
      "patient-1",
      "bead_specificity_chart_page_1",
      bead1
    )
    expect(uploadPatientReportFile).toHaveBeenCalledWith(
      "patient-1",
      "bead_specificity_chart_page_2",
      bead2
    )
  })

  it("does not re-register the pair on retry after a failed file upload", async () => {
    const hlaFile = new File(["x"], "hla.pdf")
    uploadPairReportFile.mockRejectedValueOnce(new Error("network down"))

    let caughtProgress = null
    try {
      await submitPairRegistration(baseInput({ files: { ...baseInput().files, hlaTypingReport: hlaFile } }))
    } catch (err) {
      caughtProgress = err.progress
    }

    expect(caughtProgress).toEqual(
      expect.objectContaining({ pairId: "pair-1", patientId: "patient-1", donorId: "donor-1" })
    )
    expect(createPair).toHaveBeenCalledTimes(1)

    uploadPairReportFile.mockResolvedValueOnce({ id: "file-1" })
    await submitPairRegistration(
      baseInput({ files: { ...baseInput().files, hlaTypingReport: hlaFile } }),
      caughtProgress
    )

    // Still only ever called once -- the retry resumed from progress
    // instead of re-registering the patient/donor.
    expect(createPair).toHaveBeenCalledTimes(1)
  })

  it("skips a file upload step whose progress flag is already set", async () => {
    const progress = {
      pairId: "pair-1",
      patientId: "patient-1",
      donorId: "donor-1",
      hlaTypingFileUploaded: true,
    }
    const hlaFile = new File(["x"], "hla.pdf")

    await submitPairRegistration(
      baseInput({ files: { ...baseInput().files, hlaTypingReport: hlaFile } }),
      progress
    )

    expect(createPair).not.toHaveBeenCalled()
    expect(uploadPairReportFile).not.toHaveBeenCalled()
  })
})

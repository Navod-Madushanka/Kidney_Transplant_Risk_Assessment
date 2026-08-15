// src/context/wizardReducer.test.js
import { describe, expect, it } from "vitest"
import { buildInitialWizardState, WIZARD_ACTIONS, wizardReducer } from "./wizardReducer"

describe("buildInitialWizardState", () => {
  it("starts with furthestStepIndex at 0 and one empty row per HLA locus", () => {
    const state = buildInitialWizardState()

    expect(state.furthestStepIndex).toBe(0)
    // Backend's HLA_LOCI has 9 loci (app/reference_data/hla_loci.py) —
    // patient_hla/donor_hla must always have exactly one row per locus.
    expect(state.patient_hla).toHaveLength(9)
    expect(state.donor_hla).toHaveLength(9)
    expect(state.patient_hla.every((row) => row.allele_1 === "" && row.allele_2 === "")).toBe(
      true
    )
  })

  it("starts crossmatch.is_positive unset, so ReviewStep knows to require it", () => {
    const state = buildInitialWizardState()

    // null, not false — this is "not yet confirmed", distinct from a
    // confirmed negative result. ReviewStep's validation relies on this
    // three-state distinction to block submission until the doctor has
    // actually made a call either way.
    expect(state.crossmatch.is_positive).toBeNull()
  })
})

describe("UNLOCK_STEP", () => {
  it("advances furthestStepIndex forward", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, { type: WIZARD_ACTIONS.UNLOCK_STEP, index: 2 })

    expect(next.furthestStepIndex).toBe(2)
  })

  it("never moves furthestStepIndex backward", () => {
    const state = { ...buildInitialWizardState(), furthestStepIndex: 3 }

    // Navigating back to an earlier step (e.g. clicking "Back") shouldn't
    // re-lock steps the doctor already reached.
    const next = wizardReducer(state, { type: WIZARD_ACTIONS.UNLOCK_STEP, index: 1 })

    expect(next.furthestStepIndex).toBe(3)
  })
})

describe("SET_PATIENT_DETAILS", () => {
  it("merges the patch into patient_details without touching other fields", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, {
      type: WIZARD_ACTIONS.SET_PATIENT_DETAILS,
      patch: { full_name: "Alice" },
    })

    expect(next.patient_details.full_name).toBe("Alice")
    expect(next.patient_details.blood_type).toBe("")
    // Unrelated top-level state is untouched.
    expect(next.donor_details).toBe(state.donor_details)
  })
})

describe("SET_PATIENT_HLA_ROW", () => {
  it("updates only the row matching the given locus", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, {
      type: WIZARD_ACTIONS.SET_PATIENT_HLA_ROW,
      locus: "A",
      patch: { allele_1: "29" },
    })

    const rowA = next.patient_hla.find((row) => row.locus === "A")
    const rowB = next.patient_hla.find((row) => row.locus === "B")
    expect(rowA.allele_1).toBe("29")
    expect(rowB.allele_1).toBe("")
  })
})

describe("SET_CROSSMATCH", () => {
  it("merges the patch into crossmatch without touching other fields", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, {
      type: WIZARD_ACTIONS.SET_CROSSMATCH,
      patch: { is_positive: false, t_cell_result: "Negative" },
    })

    expect(next.crossmatch.is_positive).toBe(false)
    expect(next.crossmatch.t_cell_result).toBe("Negative")
    // b_cell_result wasn't part of this patch — stays at its prior value.
    expect(next.crossmatch.b_cell_result).toBe("")
  })

  it("can flip a confirmed result back and forth without losing other fields", () => {
    const withNegative = wizardReducer(buildInitialWizardState(), {
      type: WIZARD_ACTIONS.SET_CROSSMATCH,
      patch: { is_positive: false, remarks: "Repeat crossmatch clear" },
    })

    const withPositive = wizardReducer(withNegative, {
      type: WIZARD_ACTIONS.SET_CROSSMATCH,
      patch: { is_positive: true },
    })

    expect(withPositive.crossmatch.is_positive).toBe(true)
    // Doctor's earlier remarks aren't wiped out just by changing the result.
    expect(withPositive.crossmatch.remarks).toBe("Repeat crossmatch clear")
  })
})

describe("SET_OCR_VERIFIED", () => {
  it("starts false for all three document groups", () => {
    const state = buildInitialWizardState()

    expect(state.ocr_verified).toEqual({
      details: false,
      hla_typing: false,
      bead_specificity: false,
    })
  })

  it("sets only the named group, leaving the other untouched", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, {
      type: WIZARD_ACTIONS.SET_OCR_VERIFIED,
      group: "hla_typing",
      verified: true,
    })

    expect(next.ocr_verified.hla_typing).toBe(true)
    expect(next.ocr_verified.bead_specificity).toBe(false)
  })
})

describe("HYDRATE_FROM_OCR", () => {
  it("invalidates hla_typing verification when a fresh extraction overwrites HLA rows", () => {
    const verifiedState = {
      ...buildInitialWizardState(),
      ocr_verified: { hla_typing: true, bead_specificity: true },
    }

    const next = wizardReducer(verifiedState, {
      type: WIZARD_ACTIONS.HYDRATE_FROM_OCR,
      payload: { patientHla: [{ locus: "A", allele_1: "01", allele_2: "02" }] },
    })

    // A re-upload's fresh, unreviewed HLA output shouldn't inherit the
    // doctor's earlier confirmation of the previous extraction.
    expect(next.ocr_verified.hla_typing).toBe(false)
    // Bead specificity wasn't touched by this hydrate -- stays confirmed.
    expect(next.ocr_verified.bead_specificity).toBe(true)
  })

  it("invalidates bead_specificity verification when a fresh extraction overwrites it", () => {
    const verifiedState = {
      ...buildInitialWizardState(),
      ocr_verified: { hla_typing: true, bead_specificity: true },
    }

    const next = wizardReducer(verifiedState, {
      type: WIZARD_ACTIONS.HYDRATE_FROM_OCR,
      payload: { beadSpecificity: [{ antigen: "B7", mfi: 3500 }] },
    })

    expect(next.ocr_verified.bead_specificity).toBe(false)
    expect(next.ocr_verified.hla_typing).toBe(true)
  })

  it("leaves both verification flags untouched when the OCR payload found nothing new", () => {
    const verifiedState = {
      ...buildInitialWizardState(),
      ocr_verified: { hla_typing: true, bead_specificity: true },
    }

    const next = wizardReducer(verifiedState, {
      type: WIZARD_ACTIONS.HYDRATE_FROM_OCR,
      payload: {},
    })

    expect(next.ocr_verified).toEqual({ hla_typing: true, bead_specificity: true })
  })
})

describe("HYDRATE_FROM_OCR — field merging", () => {
  it("only overwrites patient_details fields OCR actually found a value for", () => {
    const state = {
      ...buildInitialWizardState(),
      patient_details: { full_name: "Already Typed", nic_number: "", date_of_birth: "", blood_type: "" },
    }

    const next = wizardReducer(state, {
      type: WIZARD_ACTIONS.HYDRATE_FROM_OCR,
      payload: {
        patientDetails: { full_name: "", blood_type: "A" },
      },
    })

    // OCR found nothing for full_name (empty string) -> doctor's typed
    // value is preserved, not blanked out.
    expect(next.patient_details.full_name).toBe("Already Typed")
    // OCR found a blood type -> that gets applied.
    expect(next.patient_details.blood_type).toBe("A")
  })

  it("merges incoming HLA rows by locus, leaving unmatched loci untouched", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, {
      type: WIZARD_ACTIONS.HYDRATE_FROM_OCR,
      payload: {
        patientHla: [{ locus: "A", allele_1: "29", allele_2: "33" }],
      },
    })

    const rowA = next.patient_hla.find((row) => row.locus === "A")
    const rowB = next.patient_hla.find((row) => row.locus === "B")
    expect(rowA.allele_1).toBe("29")
    expect(rowA.allele_2).toBe("33")
    expect(rowB.allele_1).toBe("")
  })

  it("leaves state untouched when the OCR payload is empty", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, {
      type: WIZARD_ACTIONS.HYDRATE_FROM_OCR,
      payload: {},
    })

    expect(next.patient_hla).toEqual(state.patient_hla)
    expect(next.donor_hla).toEqual(state.donor_hla)
  })
})

describe("buildInitialWizardState extraction", () => {
  it("starts idle with no job and an empty document map", () => {
    const state = buildInitialWizardState()

    expect(state.extraction).toEqual({
      jobId: null,
      status: "idle",
      documents: {},
      error: null,
      pollingStalled: false,
    })
  })
})

describe("START_EXTRACTION_JOB", () => {
  it("seeds one pending entry per requested document type and marks the job running", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, {
      type: WIZARD_ACTIONS.START_EXTRACTION_JOB,
      jobId: "job-1",
      documentTypes: ["hla_typing_report", "crossmatch_report"],
    })

    expect(next.extraction.jobId).toBe("job-1")
    expect(next.extraction.status).toBe("running")
    expect(next.extraction.documents).toEqual({
      hla_typing_report: { status: "pending", completed: 0, total: 1, errors: [] },
      crossmatch_report: { status: "pending", completed: 0, total: 1, errors: [] },
    })
  })

  it("replaces a prior job's state entirely, discarding its old progress", () => {
    const withOldJob = wizardReducer(buildInitialWizardState(), {
      type: WIZARD_ACTIONS.SET_EXTRACTION_JOB_STATUS,
      status: "done",
      documents: { hla_typing_report: { status: "done", completed: 1, total: 1, errors: [] } },
    })

    const next = wizardReducer(withOldJob, {
      type: WIZARD_ACTIONS.START_EXTRACTION_JOB,
      jobId: "job-2",
      documentTypes: ["bead_specificity_page_1"],
    })

    expect(next.extraction.jobId).toBe("job-2")
    expect(next.extraction.status).toBe("running")
    expect(next.extraction.documents).toEqual({
      bead_specificity_page_1: { status: "pending", completed: 0, total: 1, errors: [] },
    })
  })
})

describe("SET_EXTRACTION_JOB_STATUS", () => {
  it("replaces status and documents wholesale from a poll snapshot", () => {
    const started = wizardReducer(buildInitialWizardState(), {
      type: WIZARD_ACTIONS.START_EXTRACTION_JOB,
      jobId: "job-1",
      documentTypes: ["bead_specificity_page_1"],
    })

    const next = wizardReducer(started, {
      type: WIZARD_ACTIONS.SET_EXTRACTION_JOB_STATUS,
      status: "running",
      documents: {
        bead_specificity_page_1: { status: "in_progress", completed: 3, total: 8, errors: [] },
      },
    })

    expect(next.extraction.jobId).toBe("job-1") // untouched by this action
    expect(next.extraction.status).toBe("running")
    expect(next.extraction.documents.bead_specificity_page_1).toEqual({
      status: "in_progress",
      completed: 3,
      total: 8,
      errors: [],
    })
  })
})

describe("SET_EXTRACTION_JOB_ERROR", () => {
  it("marks the job failed and records the error message", () => {
    const started = wizardReducer(buildInitialWizardState(), {
      type: WIZARD_ACTIONS.START_EXTRACTION_JOB,
      jobId: "job-1",
      documentTypes: ["hla_typing_report"],
    })

    const next = wizardReducer(started, {
      type: WIZARD_ACTIONS.SET_EXTRACTION_JOB_ERROR,
      error: "Couldn't reach the server",
    })

    expect(next.extraction.status).toBe("failed")
    expect(next.extraction.error).toBe("Couldn't reach the server")
  })
})

describe("SET_EXTRACTION_POLLING_STALLED", () => {
  it("flips pollingStalled without touching status", () => {
    const started = wizardReducer(buildInitialWizardState(), {
      type: WIZARD_ACTIONS.START_EXTRACTION_JOB,
      jobId: "job-1",
      documentTypes: ["hla_typing_report"],
    })

    const stalled = wizardReducer(started, {
      type: WIZARD_ACTIONS.SET_EXTRACTION_POLLING_STALLED,
      isStalled: true,
    })

    expect(stalled.extraction.pollingStalled).toBe(true)
    expect(stalled.extraction.status).toBe("running") // not "failed" -- polling losing contact isn't the job failing

    const recovered = wizardReducer(stalled, {
      type: WIZARD_ACTIONS.SET_EXTRACTION_POLLING_STALLED,
      isStalled: false,
    })

    expect(recovered.extraction.pollingStalled).toBe(false)
  })
})

describe("RESET", () => {
  it("returns a fresh initial state, discarding all progress", () => {
    const dirtyState = wizardReducer(buildInitialWizardState(), {
      type: WIZARD_ACTIONS.UNLOCK_STEP,
      index: 4,
    })

    const next = wizardReducer(dirtyState, { type: WIZARD_ACTIONS.RESET })

    expect(next.furthestStepIndex).toBe(0)
  })
})

describe("unknown action", () => {
  it("returns the state unchanged", () => {
    const state = buildInitialWizardState()

    const next = wizardReducer(state, { type: "NOT_A_REAL_ACTION" })

    expect(next).toBe(state)
  })
})

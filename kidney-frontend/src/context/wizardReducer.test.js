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

describe("HYDRATE_FROM_OCR", () => {
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

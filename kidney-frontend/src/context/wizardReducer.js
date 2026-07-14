// src/context/wizardReducer.js
import { HLA_LOCUS_OPTIONS } from "../constants/clinicalEnums";
import { DEFAULT_MFI_CUTOFF } from "../constants/clinical";

// One empty typing row per locus, in the canonical order — mirrors the
// backend's HLA_LOCI list so nothing is silently missing when the pipeline
// later calls get_patient_hla_typing_dict / get_donor_hla_typing_dict.
function emptyHlaRows() {
  return HLA_LOCUS_OPTIONS.map((option) => ({
    locus: option.value,
    allele_1: "",
    allele_2: "",
  }));
}

export function buildInitialWizardState() {
  return {
    // Phase 3 — raw uploads, keyed by what they contain rather than by
    // "patient"/"donor" position alone, since a mislabeled photo is a real
    // clinical risk. Values are File objects (or null) held only in memory;
    // OCR extraction results (if any) land in the structured fields below.
    photos: {
      hlaTypingReport: null,      // joint patient+donor HLA typing report
      beadSpecificityPage1: null, // bead specificity chart, page 1
      beadSpecificityPage2: null, // bead specificity chart, page 2 (report can run longer; page 2 is "at least the next page", not "the last page")
      crossmatchReport: null,     // T-cell/B-cell crossmatch + compatibility verdict
    },

    // Phase 4 — Payload 1
    patient_details: {
      full_name: "",
      nic_number: "",
      date_of_birth: "",
      blood_type: "",
    },
    donor_details: {
      full_name: "",
      nic_number: "",
      date_of_birth: "",
      blood_type: "",
    },

    // Phase 5 — Payload 2
    patient_hla: emptyHlaRows(),
    donor_hla: emptyHlaRows(),

    // Phase 6 — sensitization booleans + MFI cutoff (sent alongside Payload 3)
    sensitization: {
      previous_transplant: false,
      pregnancy: false,
      blood_transfusion: false,
    },
    mfi_cutoff: DEFAULT_MFI_CUTOFF,

    // Phase 7 — Payload 3
    bead_specificity: [],

    // Wizard navigation guard: the furthest step the doctor has actually
    // reached, so ProtectedRoute-style guards can block jumping ahead via a
    // typed URL, while still allowing free navigation backward.
    furthestStepIndex: 0,
  };
}

export const WIZARD_ACTIONS = {
  SET_PHOTO: "SET_PHOTO",
  SET_PATIENT_DETAILS: "SET_PATIENT_DETAILS",
  SET_DONOR_DETAILS: "SET_DONOR_DETAILS",
  SET_PATIENT_HLA_ROW: "SET_PATIENT_HLA_ROW",
  SET_DONOR_HLA_ROW: "SET_DONOR_HLA_ROW",
  SET_SENSITIZATION: "SET_SENSITIZATION",
  SET_MFI_CUTOFF: "SET_MFI_CUTOFF",
  SET_BEAD_SPECIFICITY: "SET_BEAD_SPECIFICITY",
  UNLOCK_STEP: "UNLOCK_STEP",
  RESET: "RESET",
};

function updateHlaRow(rows, locus, patch) {
  return rows.map((row) => (row.locus === locus ? { ...row, ...patch } : row));
}

export function wizardReducer(state, action) {
  switch (action.type) {
    case WIZARD_ACTIONS.SET_PHOTO:
      return {
        ...state,
        photos: { ...state.photos, [action.slot]: action.file },
      };

    case WIZARD_ACTIONS.SET_PATIENT_DETAILS:
      return {
        ...state,
        patient_details: { ...state.patient_details, ...action.patch },
      };

    case WIZARD_ACTIONS.SET_DONOR_DETAILS:
      return {
        ...state,
        donor_details: { ...state.donor_details, ...action.patch },
      };

    case WIZARD_ACTIONS.SET_PATIENT_HLA_ROW:
      return {
        ...state,
        patient_hla: updateHlaRow(state.patient_hla, action.locus, action.patch),
      };

    case WIZARD_ACTIONS.SET_DONOR_HLA_ROW:
      return {
        ...state,
        donor_hla: updateHlaRow(state.donor_hla, action.locus, action.patch),
      };

    case WIZARD_ACTIONS.SET_SENSITIZATION:
      return {
        ...state,
        sensitization: { ...state.sensitization, ...action.patch },
      };

    case WIZARD_ACTIONS.SET_MFI_CUTOFF:
      return { ...state, mfi_cutoff: action.value };

    case WIZARD_ACTIONS.SET_BEAD_SPECIFICITY:
      return { ...state, bead_specificity: action.rows };

    case WIZARD_ACTIONS.UNLOCK_STEP:
      return {
        ...state,
        furthestStepIndex: Math.max(state.furthestStepIndex, action.index),
      };

    case WIZARD_ACTIONS.RESET:
      return buildInitialWizardState();

    default:
      return state;
  }
}
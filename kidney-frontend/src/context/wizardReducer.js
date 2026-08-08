import { HLA_LOCUS_OPTIONS } from "../constants/clinicalEnums";

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
      rh_factor: "",
    },
    donor_details: {
      full_name: "",
      nic_number: "",
      date_of_birth: "",
      blood_type: "",
      rh_factor: "",
    },

    // Phase 5 — Payload 2
    patient_hla: emptyHlaRows(),
    donor_hla: emptyHlaRows(),

    // Phase 6 — sensitization booleans (sent alongside Payload 3). No MFI
    // cutoff field here — the wizard used to show an editable "adjusted
    // cutoff" preview, but it was never actually sent to the backend, which
    // always recomputes Step 2 from its own fixed default and never used
    // the preview to adjust the real Step 5 DSA check either (see
    // app/reference_data/dsa_threshold.py) — removed 2026-08-08 rather than
    // leaving a doctor-facing field that silently did nothing.
    sensitization: {
      previous_transplant: false,
      pregnancy: false,
      blood_transfusion: false,
    },
    sensitization_dates: {
      previous_transplant: "",
      pregnancy: "",
      blood_transfusion: "",
    },

    // Phase 7 — Payload 3
    bead_specificity: [],
    // t_cell_result / b_cell_result / interpretation / remarks / test_date
    // may get pre-filled by OCR extraction on the photos step, giving the
    // doctor a head start rather than a blank form. is_positive is never
    // OCR-filled — it's the doctor's own confirmed reading of the
    // crossmatch result, entered on the Review step, and is what actually
    // gates Step 6 of the backend pipeline (see
    // CompatibilityCheckRequest.crossmatch in app/schemas/match_report.py).
    // interpretation and test_date stay reference-only — the backend's
    // CrossmatchInput schema doesn't have fields for them.
    crossmatch: {
      is_positive: null,
      t_cell_result: "",
      b_cell_result: "",
      interpretation: "",
      remarks: "",
      test_date: "",
    },

    // Wizard navigation guard: the furthest step the doctor has actually
    // reached, so ProtectedRoute-style guards can block jumping ahead via a
    // typed URL, while still allowing free navigation backward.
    furthestStepIndex: 0,

    // Tracks the current/last document-extraction job, if any. Lives here
    // (rather than as PhotoUploadsStep local state) specifically so it
    // survives navigating to another wizard step — extraction runs as a
    // background job on kidney-backend (see app/services/ocr_job_service.py)
    // that keeps going regardless of which page is open, and
    // WizardProvider's polling effect (not any one step component) is what
    // watches jobId and feeds completed documents into the fields above via
    // HYDRATE_FROM_OCR. Without this living at the wizard level, navigating
    // away from Photos mid-extraction used to silently kill every visible
    // sign of progress even though the extraction itself kept running.
    extraction: {
      jobId: null,
      status: "idle", // idle | running | done | failed
      documents: {}, // { [document_type]: { status, completed, total, errors, ... } } -- last poll snapshot
      error: null,
    },
  };
}

export const WIZARD_ACTIONS = {
  SET_PHOTO: "SET_PHOTO",
  SET_PATIENT_DETAILS: "SET_PATIENT_DETAILS",
  SET_DONOR_DETAILS: "SET_DONOR_DETAILS",
  SET_PATIENT_HLA_ROW: "SET_PATIENT_HLA_ROW",
  SET_DONOR_HLA_ROW: "SET_DONOR_HLA_ROW",
  SET_SENSITIZATION: "SET_SENSITIZATION",
  SET_BEAD_SPECIFICITY: "SET_BEAD_SPECIFICITY",
  SET_CROSSMATCH: "SET_CROSSMATCH",
  HYDRATE_FROM_OCR: "HYDRATE_FROM_OCR",
  UNLOCK_STEP: "UNLOCK_STEP",
  RESET: "RESET",
  SET_SENSITIZATION_DATE: "SET_SENSITIZATION_DATE",
  START_EXTRACTION_JOB: "START_EXTRACTION_JOB",
  SET_EXTRACTION_JOB_STATUS: "SET_EXTRACTION_JOB_STATUS",
  SET_EXTRACTION_JOB_ERROR: "SET_EXTRACTION_JOB_ERROR",
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

    case WIZARD_ACTIONS.SET_BEAD_SPECIFICITY:
      return { ...state, bead_specificity: action.rows };

    case WIZARD_ACTIONS.SET_CROSSMATCH:
      return {
        ...state,
        crossmatch: { ...state.crossmatch, ...action.patch },
      };

    case WIZARD_ACTIONS.HYDRATE_FROM_OCR: {
      const { patientDetails, donorDetails, patientHla, donorHla, beadSpecificity, crossmatch } =
        action.payload;

      // Only overwrite a field if OCR actually found something — never
      // blank out a value the doctor already typed in by hand.
      const mergeDetails = (existing, incoming) => {
        const next = { ...existing };
        for (const [key, value] of Object.entries(incoming || {})) {          if (value) next[key] = value;
        }
        return next;
      };

      // Matches incoming OCR rows to existing rows by locus (both sides
      // use the same canonical HLA_LOCI codes), leaving any locus OCR
      // didn't find untouched.
      const mergeHlaRows = (existingRows, incomingRows) => {
        if (!incomingRows || incomingRows.length === 0) return existingRows;
        return existingRows.map((row) => {
          const match = incomingRows.find((r) => r.locus === row.locus);
          if (!match) return row;
          return {
            ...row,
            allele_1: match.allele_1 || match.allele1 || row.allele_1,
            allele_2: match.allele_2 || match.allele2 || row.allele_2,
          };
        });
      };

      return {
        ...state,
        patient_details: mergeDetails(state.patient_details, patientDetails),
        donor_details: mergeDetails(state.donor_details, donorDetails),
        patient_hla: mergeHlaRows(state.patient_hla, patientHla),
        donor_hla: mergeHlaRows(state.donor_hla, donorHla),
        bead_specificity:
          beadSpecificity && beadSpecificity.length > 0 ? beadSpecificity : state.bead_specificity,
        crossmatch: crossmatch ? { ...state.crossmatch, ...crossmatch } : state.crossmatch,
      };
    }

    case WIZARD_ACTIONS.UNLOCK_STEP:
      return {
        ...state,
        furthestStepIndex: Math.max(state.furthestStepIndex, action.index),
      };

    case WIZARD_ACTIONS.RESET:
      return buildInitialWizardState();

    case WIZARD_ACTIONS.SET_SENSITIZATION_DATE:
      return {
        ...state,
        sensitization_dates: {
          ...state.sensitization_dates,
          [action.eventType]: action.date,
        },
      };

    // Fired the moment POST /ocr/extract-batch/jobs returns a job_id --
    // seeds one "pending" entry per requested document so the progress
    // list has something to show immediately, before the background job
    // has even started running.
    case WIZARD_ACTIONS.START_EXTRACTION_JOB: {
      const documents = {};
      for (const documentType of action.documentTypes) {
        documents[documentType] = { status: "pending", completed: 0, total: 1, errors: [] };
      }
      return {
        ...state,
        extraction: { jobId: action.jobId, status: "running", documents, error: null },
      };
    }

    // Applies one GET .../jobs/{id} poll response -- a full snapshot, not
    // a delta, so this just replaces extraction.documents/status wholesale
    // rather than merging. WizardProvider's polling effect is what decides
    // when a document has newly finished and dispatches HYDRATE_FROM_OCR
    // for it separately; this action only updates the progress list itself.
    case WIZARD_ACTIONS.SET_EXTRACTION_JOB_STATUS:
      return {
        ...state,
        extraction: {
          ...state.extraction,
          status: action.status,
          documents: action.documents,
        },
      };

    // A poll request itself failed (network blip, server error) rather
    // than the job failing -- distinct from a document-level error, which
    // lives in extraction.documents[...].errors and doesn't stop the job.
    case WIZARD_ACTIONS.SET_EXTRACTION_JOB_ERROR:
      return {
        ...state,
        extraction: { ...state.extraction, status: "failed", error: action.error },
      };

    default:
      return state;
  }
}
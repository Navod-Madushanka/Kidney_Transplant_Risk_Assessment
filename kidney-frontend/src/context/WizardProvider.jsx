// src/context/WizardProvider.jsx
import { useMemo, useReducer } from "react";
import { useLocation } from "react-router-dom";
import { WizardContext } from "./WizardContext";
import {
  buildInitialWizardState,
  wizardReducer,
  WIZARD_ACTIONS,
} from "./wizardReducer";
import { useExtractionJobPolling } from "../hooks/useExtractionJobPolling";

export function WizardProvider({ children }) {
  // NewCheckFromRecordsPage.jsx navigates here with
  // `state: { prefillPhotos }` when a doctor starts a check from an
  // existing patient/donor's archived report files, so the Photos step
  // opens with those slots already filled in -- same as if the doctor had
  // picked the files themselves. Read via useReducer's lazy-init argument
  // (not an effect) so it's applied exactly once, at the initial state
  // construction, and never re-runs on later in-wizard navigation.
  const location = useLocation();

  const [state, dispatch] = useReducer(
    wizardReducer,
    location.state?.prefillPhotos,
    (prefillPhotos) => {
      const initial = buildInitialWizardState();
      if (!prefillPhotos) return initial;
      return { ...initial, photos: { ...initial.photos, ...prefillPhotos } };
    }
  );

  // Lives here rather than in PhotoUploadsStep so the poll loop survives
  // navigating to any other wizard step -- see
  // useExtractionJobPolling.js's docstring and extraction's own comment in
  // wizardReducer.js's buildInitialWizardState.
  useExtractionJobPolling(dispatch, state.extraction.jobId, state.extraction.status);

  const actions = useMemo(
    () => ({
      setPhoto: (slot, file) =>
        dispatch({ type: WIZARD_ACTIONS.SET_PHOTO, slot, file }),

      setPatientDetails: (patch) =>
        dispatch({ type: WIZARD_ACTIONS.SET_PATIENT_DETAILS, patch }),

      setDonorDetails: (patch) =>
        dispatch({ type: WIZARD_ACTIONS.SET_DONOR_DETAILS, patch }),

      setPatientHlaRow: (locus, patch) =>
        dispatch({ type: WIZARD_ACTIONS.SET_PATIENT_HLA_ROW, locus, patch }),

      setDonorHlaRow: (locus, patch) =>
        dispatch({ type: WIZARD_ACTIONS.SET_DONOR_HLA_ROW, locus, patch }),

      setSensitization: (patch) =>
        dispatch({ type: WIZARD_ACTIONS.SET_SENSITIZATION, patch }),

      setOcrVerified: (group, verified) =>
        dispatch({ type: WIZARD_ACTIONS.SET_OCR_VERIFIED, group, verified }),

      setBeadSpecificity: (rows) =>
        dispatch({ type: WIZARD_ACTIONS.SET_BEAD_SPECIFICITY, rows }),

      setCrossmatch: (patch) =>
        dispatch({ type: WIZARD_ACTIONS.SET_CROSSMATCH, patch }),

      unlockStep: (index) =>
        dispatch({ type: WIZARD_ACTIONS.UNLOCK_STEP, index }),
      
      setSensitizationDate: (eventType, date) =>
        dispatch({ type: WIZARD_ACTIONS.SET_SENSITIZATION_DATE, eventType, date }),

      hydrateFromOcr: (payload) =>
        dispatch({ type: WIZARD_ACTIONS.HYDRATE_FROM_OCR, payload }),

      startExtractionJob: (jobId, documentTypes) =>
        dispatch({ type: WIZARD_ACTIONS.START_EXTRACTION_JOB, jobId, documentTypes }),

      reset: () => dispatch({ type: WIZARD_ACTIONS.RESET }),
    }),
    []
  );

  // state and actions are exposed separately (rather than spread into one
  // flat object) so consuming components can destructure `{ state }` for
  // read-only rendering vs `{ actions }` for event handlers, which makes it
  // obvious at a glance whether a given line reads or mutates wizard data.
  const value = useMemo(() => ({ state, actions }), [state, actions]);

  return (
    <WizardContext.Provider value={value}>{children}</WizardContext.Provider>
  );
}
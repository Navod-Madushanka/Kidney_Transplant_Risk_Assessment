// src/context/WizardProvider.jsx
import { useMemo, useReducer } from "react";
import { WizardContext } from "./WizardContext";
import {
  buildInitialWizardState,
  wizardReducer,
  WIZARD_ACTIONS,
} from "./wizardReducer";

export function WizardProvider({ children }) {
  const [state, dispatch] = useReducer(
    wizardReducer,
    undefined,
    buildInitialWizardState
  );

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

      setMfiCutoff: (value) =>
        dispatch({ type: WIZARD_ACTIONS.SET_MFI_CUTOFF, value }),

      setBeadSpecificity: (rows) =>
        dispatch({ type: WIZARD_ACTIONS.SET_BEAD_SPECIFICITY, rows }),

      unlockStep: (index) =>
        dispatch({ type: WIZARD_ACTIONS.UNLOCK_STEP, index }),
      
      setSensitizationDate: (eventType, date) =>
        dispatch({ type: WIZARD_ACTIONS.SET_SENSITIZATION_DATE, eventType, date }),

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
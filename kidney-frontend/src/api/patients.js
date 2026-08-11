// src/api/patients.js
import { apiDelete, apiGet, apiPost, apiPut } from "./client"

export const listPatients = () => apiGet("/patients") // requires the list endpoint above
export const createPatient = (payload) => apiPost("/patients", payload)
export const getPatient = (id) => apiGet(`/patients/${id}`)
export const updatePatient = (id, payload) => apiPut(`/patients/${id}`, payload)
export const deletePatient = (id) => apiDelete(`/patients/${id}`)
// ocrVerified is omitted (undefined) for the common case of a manual edit
// (e.g. via the patient detail page's HLA typing editor) -- the backend
// treats that as "not an OCR write, no claim being made" and trusts it.
// The compatibility-check wizard is the only caller that ever passes an
// explicit true/false, when the source document was OCR-extracted (see
// SET_OCR_VERIFIED in wizardReducer.js). See
// kidney-backend/app/api/patients.py's matching endpoint docstrings.
export const replacePatientHlaTypings = (id, entries, ocrVerified) =>
  apiPut(
    `/patients/${id}/hla-typings${ocrVerified === undefined ? "" : `?ocr_verified=${ocrVerified}`}`,
    entries
  )
export const replacePatientAntibodyProfiles = (id, entries, ocrVerified) =>
  apiPut(
    `/patients/${id}/antibody-profiles${ocrVerified === undefined ? "" : `?ocr_verified=${ocrVerified}`}`,
    entries
  )
export const createSensitizationEvents = (id, entries) => apiPost(`/patients/${id}/sensitization-events`, entries)
// Replace semantics (delete-then-insert), unlike createSensitizationEvents
// above -- see the matching backend endpoint's docstring. Used by the
// compatibility-check wizard, which re-submits the full current set on
// every check rather than appending to whatever's already there.
export const replacePatientSensitizationEvents = (id, entries) =>
  apiPut(`/patients/${id}/sensitization-events`, entries)
export const getPatientReports = (id) => apiGet(`/patients/${id}/reports`)
export const getPatientHlaTypings = (id) => apiGet(`/patients/${id}/hla-typings`)
export const getPatientAntibodyProfiles = (id) => apiGet(`/patients/${id}/antibody-profiles`)
export const listPatientSensitizationEvents = (id) => apiGet(`/patients/${id}/sensitization-events`)
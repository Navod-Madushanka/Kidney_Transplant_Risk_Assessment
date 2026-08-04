// src/api/patients.js
import { apiDelete, apiGet, apiPost, apiPut } from "./client"

export const listPatients = () => apiGet("/patients") // requires the list endpoint above
export const createPatient = (payload) => apiPost("/patients", payload)
export const getPatient = (id) => apiGet(`/patients/${id}`)
export const updatePatient = (id, payload) => apiPut(`/patients/${id}`, payload)
export const deletePatient = (id) => apiDelete(`/patients/${id}`)
export const replacePatientHlaTypings = (id, entries) => apiPut(`/patients/${id}/hla-typings`, entries)
export const replacePatientAntibodyProfiles = (id, entries) => apiPut(`/patients/${id}/antibody-profiles`, entries)
export const createSensitizationEvents = (id, entries) => apiPost(`/patients/${id}/sensitization-events`, entries)
export const getPatientReports = (id) => apiGet(`/patients/${id}/reports`)
export const getPatientHlaTypings = (id) => apiGet(`/patients/${id}/hla-typings`)
export const getPatientAntibodyProfiles = (id) => apiGet(`/patients/${id}/antibody-profiles`)
export const listPatientSensitizationEvents = (id) => apiGet(`/patients/${id}/sensitization-events`)
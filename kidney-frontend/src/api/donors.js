// src/api/donors.js
import { apiDelete, apiGet, apiPost, apiPut } from "./client"

export const listDonors = () => apiGet("/donors") // requires the list endpoint above
export const createDonor = (payload) => apiPost("/donors", payload)
export const getDonor = (id) => apiGet(`/donors/${id}`)
export const updateDonor = (id, payload) => apiPut(`/donors/${id}`, payload)
export const deleteDonor = (id) => apiDelete(`/donors/${id}`)
// See replacePatientHlaTypings in api/patients.js for ocrVerified's contract.
export const replaceDonorHlaTypings = (id, entries, ocrVerified) =>
  apiPut(
    `/donors/${id}/hla-typings${ocrVerified === undefined ? "" : `?ocr_verified=${ocrVerified}`}`,
    entries
  )
export const getDonorHlaTypings = (id) => apiGet(`/donors/${id}/hla-typings`)
export const updateDonorStatus = (id, status) => apiPut(`/donors/${id}/status`, { status })
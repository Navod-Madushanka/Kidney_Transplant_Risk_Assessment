// src/api/pairs.js
// Wrappers for POST /pairs (joint patient+donor registration, see
// NewPairPage.jsx) and the pair lookup endpoints the patient/donor detail
// pages use to render their read-only "Pair documents" card.
import { apiGet, apiPost } from "./client"

export const createPair = (payload) => apiPost("/pairs", payload)

export const getPair = (id) => apiGet(`/pairs/${id}`)

// patientId/donorId are both optional filters -- pass whichever the caller
// has (DonorDetailPage passes donorId, PatientDetailPage passes patientId).
export const listPairs = ({ patientId, donorId } = {}) => {
  const params = new URLSearchParams()
  if (patientId) params.set("patient_id", patientId)
  if (donorId) params.set("donor_id", donorId)
  const query = params.toString()
  return apiGet(`/pairs${query ? `?${query}` : ""}`)
}

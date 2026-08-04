// src/api/donorSearch.js
import { apiGet } from "./client"

export const searchCompatibleDonors = (patientId) =>
  apiGet(`/patients/${patientId}/compatible-donors`)

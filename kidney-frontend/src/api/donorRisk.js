// src/api/donorRisk.js
import { apiGet } from "./client"

export const getDonorRiskAssessment = (donorId) => apiGet(`/donors/${donorId}/risk-assessment`)

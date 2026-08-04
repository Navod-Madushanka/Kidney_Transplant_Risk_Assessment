// src/api/compatibility.js
import { apiPost } from "./client"

// The wizard (compatibilityWizard.js) posts to this same endpoint inline as
// part of its multi-step submission — this wrapper is for running a check
// directly against two already-existing records (e.g. from donor search),
// with no patient/donor creation step involved.
export const runCompatibilityCheck = (patientId, donorId) =>
  apiPost("/compatibility/check", { patient_id: patientId, donor_id: donorId })

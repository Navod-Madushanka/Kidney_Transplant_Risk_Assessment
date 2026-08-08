// src/constants/sensitizationWeights.js
//
// Mirrors the backend's SENSITIZATION_EVENT_WEIGHTS (see
// kidney-backend/app/reference_data/sensitization_weights.py). Used here
// only to show a live points preview as the doctor toggles sensitizing
// events — the backend recomputes this itself via
// calculate_sensitization_score and is the source of truth. If the backend
// weights ever change, update both places in the same PR.

export const SENSITIZATION_EVENT_WEIGHTS = {
  previous_transplant: 2.0,
  pregnancy: 1.0,
  blood_transfusion: 0.5,
}

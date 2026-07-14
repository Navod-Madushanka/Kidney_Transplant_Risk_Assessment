// src/constants/sensitizationWeights.js
//
// Mirrors the backend's SENSITIZATION_EVENT_WEIGHTS and
// SENSITIZATION_CUTOFF_REDUCTION_FACTOR (see
// kidney-backend/app/reference_data/sensitization_weights.py). Used here
// only to show a live preview of the adjusted MFI cutoff as the doctor
// toggles events — the backend still recomputes this itself via
// calculate_sensitization_score and is the source of truth. If the backend
// weights ever change, update both places in the same PR.

export const SENSITIZATION_EVENT_WEIGHTS = {
  previous_transplant: 2.0,
  pregnancy: 1.0,
  blood_transfusion: 0.5,
}

export const SENSITIZATION_CUTOFF_REDUCTION_FACTOR = 100.0
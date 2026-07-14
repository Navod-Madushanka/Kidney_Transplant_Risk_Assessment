// src/constants/clinical.js
//
// Mirrors the backend's DEFAULT_MFI_CUTOFF (see
// kidney-backend/app/services/dsa_service.py). Kept as a separate frontend
// constant rather than fetched from the backend, same rationale as
// src/constants/ocr.js — small, stable, and if it ever changes on the
// backend, update both places in the same PR.
//
// This is the *starting* value shown in the Phase 6 MFI cutoff field —
// sensitization events (previous_transplant/pregnancy/blood_transfusion)
// reduce it from here, matching calculate_sensitization_score's
// adjusted_mfi_cutoff formula. The doctor is adjusting a suggested value,
// not entering one blind.

export const DEFAULT_MFI_CUTOFF = 2000
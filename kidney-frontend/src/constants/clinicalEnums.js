// src/constants/clinicalEnums.js
//
// Values here are confirmed against the backend's app/models/enums.py.
// If the backend enums ever change, update both places together.

export const RH_FACTOR_OPTIONS = [
  { value: "+", label: "Positive (+)" },
  { value: "-", label: "Negative (-)" },
]

export const BLOOD_TYPE_OPTIONS = [
  { value: "A", label: "A" },
  { value: "B", label: "B" },
  { value: "AB", label: "AB" },
  { value: "O", label: "O" },
]

export const HLA_LOCUS_OPTIONS = [
  { value: "A", label: "HLA-A" },
  { value: "B", label: "HLA-B" },
  { value: "C", label: "HLA-C" },
  { value: "DRB1", label: "HLA-DRB1" },
  { value: "DRB3,4,5", label: "HLA-DRB3/4/5" },
  { value: "DQA1", label: "HLA-DQA1" },
  { value: "DQB1", label: "HLA-DQB1" },
  { value: "DPA1", label: "HLA-DPA1" },
  { value: "DPB1", label: "HLA-DPB1" },
]

// Matches app.models.enums.SensitizationEventTypeEnum exactly — these
// values are sent as-is in POST /patients/{id}/sensitization-events.
export const SENSITIZATION_EVENT_OPTIONS = [
  { value: "previous_transplant", label: "Previous transplant" },
  { value: "pregnancy", label: "Prior pregnancy" },
  { value: "blood_transfusion", label: "Blood transfusion" },
]

// Donor safety-assessment fields (app.models.enums.Sex/Race/SmokingStatus).
// All three backend columns are nullable, so DonorForm prepends its own
// "Unknown" option to these lists rather than that living here — see
// UNKNOWN_OPTION in DonorForm.jsx.
export const SEX_OPTIONS = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
]

// "Other" is not a validated category for the risk-projection model this
// feeds (see app/reference_data/donor_risk_model.py) — it's scored against
// the White coefficients as the best available stand-in. DonorSafety
// AssessmentPage surfaces that as a permanent disclaimer, not this label.
export const RACE_OPTIONS = [
  { value: "black", label: "Black" },
  { value: "white", label: "White" },
  { value: "other", label: "Other" },
]

export const SMOKING_STATUS_OPTIONS = [
  { value: "never", label: "Never" },
  { value: "former", label: "Former" },
  { value: "current", label: "Current" },
]
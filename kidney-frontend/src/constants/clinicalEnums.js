// src/constants/clinicalEnums.js
//
// Values here are confirmed against the backend's app/models/enums.py.
// If the backend enums ever change, update both places together.

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
  { value: "pregnancy", label: "Pregnancy" },
  { value: "blood_transfusion", label: "Blood transfusion" },
]
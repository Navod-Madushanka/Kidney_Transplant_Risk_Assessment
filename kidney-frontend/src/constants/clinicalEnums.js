// src/constants/clinicalEnums.js
//
// ASSUMPTION — please replace with the real values from app/models/enums.py.
// Inferred from box_utils.py's BLOOD_GROUP_MAP (which reduces everything down
// to these four) and the roadmap's HLA weight table / sensitization scoring.
// Wrong values here = a 422 on every submit, not a visual bug — worth
// confirming before you rely on these forms.

export const BLOOD_TYPE_OPTIONS = [
  { value: "A", label: "A" },
  { value: "B", label: "B" },
  { value: "AB", label: "AB" },
  { value: "O", label: "O" },
]

export const HLA_LOCUS_OPTIONS = [
  { value: "A", label: "HLA-A" },
  { value: "B", label: "HLA-B" },
  { value: "DRB1", label: "HLA-DRB1" },
  { value: "DQB1", label: "HLA-DQB1" },
  { value: "DPB1", label: "HLA-DPB1" },
]

export const SENSITIZATION_EVENT_OPTIONS = [
  { value: "PREVIOUS_TRANSPLANT", label: "Previous transplant" },
  { value: "PREGNANCY", label: "Pregnancy" },
  { value: "TRANSFUSION", label: "Blood transfusion" },
]
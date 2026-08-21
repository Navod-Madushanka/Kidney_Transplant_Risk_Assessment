// src/utils/antigenFormat.js
//
// The DSA check matches antibody antigens by exact string equality against
// donor typing built as a bare serological designation ("B44") -- see
// hla_antigen_designation() in kidney-backend/app/services/hla_typing_service.py.
// An allele-level HLA designation ("B*44:02") is a different, unmapped
// naming scheme entirely and can never match, no matter what the donor's
// real typing is. Mirrors the backend's AntibodyProfileEntry validator
// (app/schemas/antibody_profile.py) so a doctor gets caught here instead of
// only learning about it from a 422 after Save.

export function isAlleleLevelAntigen(value) {
  return value.includes("*") || value.includes(":")
}

export const ALLELE_LEVEL_ANTIGEN_ERROR =
  "Enter the serological designation (e.g. \"B44\"), not an allele-level typing (e.g. \"B*44:02\") -- it won't match donor typing in that format"

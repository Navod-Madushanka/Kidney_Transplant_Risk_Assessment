// src/utils/formValue.js
//
// Conversions between nullable API values (bool | null, string enum | null)
// and the string-only values SegmentedControl/InputField work with. Shared
// between DonorForm (building a submit payload) and pages that build that
// form's `initialValues` from an already-loaded record (e.g.
// DonorDetailPage) — kept out of DonorForm.jsx itself because a component
// file may only export components under this project's Fast Refresh lint
// rule (react-refresh/only-export-components).

// A nullable boolean field (unknown/no/yes) shouldn't default an unassessed
// record to a confirmed "no" — these convert between that tri-state and a
// plain SegmentedControl string value.
export const TRI_STATE_OPTIONS = [
  { value: "unknown", label: "Unknown" },
  { value: "no", label: "No" },
  { value: "yes", label: "Yes" },
]

export function boolToTriState(value) {
  if (value === true) return "yes"
  if (value === false) return "no"
  return "unknown"
}

export function triStateToBool(value) {
  if (value === "yes") return true
  if (value === "no") return false
  return null
}

// Same "don't default to a real value" reasoning as the tri-state booleans
// above, generalized to a nullable string-enum field (e.g. sex, race,
// smoking status).
export const UNKNOWN_OPTION = { value: "unknown", label: "Unknown" }

export function withUnknownOption(options) {
  return [UNKNOWN_OPTION, ...options]
}

export function enumToForm(value) {
  return value ?? "unknown"
}

export function formToEnum(value) {
  return value === "unknown" ? null : value
}

export function numberOrNull(value) {
  return value === "" ? null : Number(value)
}

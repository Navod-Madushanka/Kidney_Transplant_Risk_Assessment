// src/constants/reportFileCategory.js
//
// Mirrors kidney-backend/app/models/enums.py::ReportFileCategory and its
// PAIR_REPORT_CATEGORIES/PATIENT_REPORT_CATEGORIES split -- the two joint
// lab documents (HLA typing, crossmatch) are owned by a DonorPatientPair,
// not either person, and the backend 422s an upload to the wrong owner.

export const PAIR_REPORT_CATEGORY_OPTIONS = [
  { value: "hla_typing_report", label: "HLA Typing Report" },
  { value: "crossmatch_report", label: "Crossmatch Report" },
]

export const PATIENT_REPORT_CATEGORY_OPTIONS = [
  { value: "bead_specificity_chart_page_1", label: "Bead Specificity Chart — Page 1" },
  { value: "bead_specificity_chart_page_2", label: "Bead Specificity Chart — Page 2" },
]

// Every value, including the legacy "other" category, which nothing can
// upload to anymore but existing rows may still reference -- so a label is
// still needed for it wherever a legacy file gets rendered.
const ALL_CATEGORY_OPTIONS = [
  ...PAIR_REPORT_CATEGORY_OPTIONS,
  ...PATIENT_REPORT_CATEGORY_OPTIONS,
  { value: "other", label: "Other" },
]

const CATEGORY_LABELS = Object.fromEntries(
  ALL_CATEGORY_OPTIONS.map((opt) => [opt.value, opt.label])
)

export function reportFileCategoryLabel(category) {
  return CATEGORY_LABELS[category] ?? category
}

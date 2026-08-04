// src/constants/reportFileCategory.js
//
// Mirrors kidney-backend/app/models/enums.py::ReportFileCategory.

export const REPORT_FILE_CATEGORY_OPTIONS = [
  { value: "hla_typing_report", label: "HLA Typing Report" },
  { value: "crossmatch_report", label: "Crossmatch Report" },
  { value: "bead_specificity_chart", label: "Bead Specificity Chart" },
  { value: "other", label: "Other" },
]

const CATEGORY_LABELS = Object.fromEntries(
  REPORT_FILE_CATEGORY_OPTIONS.map((opt) => [opt.value, opt.label])
)

export function reportFileCategoryLabel(category) {
  return CATEGORY_LABELS[category] ?? category
}

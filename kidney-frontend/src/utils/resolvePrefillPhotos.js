// src/utils/resolvePrefillPhotos.js
//
// Maps an existing patient's and donor's archived report files (see
// ReportFilesCard / app/services/report_file_service.py) onto the
// compatibility-check wizard's four photo slots (see PhotoUploadsStep.jsx's
// UPLOAD_SLOTS), so a doctor starting a new check for a known patient/donor
// pair doesn't have to re-locate and re-upload documents that are already
// on file. Pure and side-effect free -- NewCheckFromRecordsPage.jsx does the
// actual blob fetching once this has decided which files (if any) apply.

// The joint HLA typing / crossmatch reports (a single document covering
// both patient and donor) may have been archived under either side --
// prefer the patient's copy, fall back to the donor's. Bead specificity is
// a patient-only test (antibody screening against a bead panel; donors
// don't have one in this domain model — see AntibodyProfileEditor, which
// only ever appears on PatientDetailPage), so it never falls back to the
// donor's archive.
export const PREFILL_SLOTS = [
  {
    slot: "hlaTypingReport",
    label: "HLA Typing Report",
    category: "hla_typing_report",
    allowDonorFallback: true,
  },
  {
    slot: "crossmatchReport",
    label: "Crossmatch Report",
    category: "crossmatch_report",
    allowDonorFallback: true,
  },
  {
    slot: "beadSpecificityPage1",
    label: "Bead Specificity Chart — Page 1",
    category: "bead_specificity_chart_page_1",
    allowDonorFallback: false,
  },
  {
    slot: "beadSpecificityPage2",
    label: "Bead Specificity Chart — Page 2",
    category: "bead_specificity_chart_page_2",
    allowDonorFallback: false,
  },
]

/**
 * patientFiles / donorFiles: arrays as returned by GET .../report-files
 * (each { id, category, original_filename, content_type, size_bytes, ... }).
 *
 * Returns one entry per wizard slot: `null` if nothing archived matches, or
 * `{ source: "patient" | "donor", reportFile }` naming which record's
 * archive it came from.
 */
export function resolvePrefillPhotos(patientFiles = [], donorFiles = []) {
  const result = {}

  for (const { slot, category, allowDonorFallback } of PREFILL_SLOTS) {
    const patientMatch = patientFiles.find((f) => f.category === category)
    const donorMatch = allowDonorFallback ? donorFiles.find((f) => f.category === category) : null
    const match = patientMatch || donorMatch

    result[slot] = match ? { source: patientMatch ? "patient" : "donor", reportFile: match } : null
  }

  return result
}

// src/utils/resolvePrefillPhotos.js
//
// Maps an existing pair's and patient's archived report files (see
// ReportFilesCard / app/services/report_file_service.py) onto the
// compatibility-check wizard's four photo slots (see PhotoUploadsStep.jsx's
// UPLOAD_SLOTS), so a doctor starting a new check for a known patient/donor
// pair doesn't have to re-locate and re-upload documents that are already
// on file. Pure and side-effect free -- NewCheckFromRecordsPage.jsx does the
// actual blob fetching once this has decided which files (if any) apply.

// The joint HLA typing / crossmatch reports (a single document covering
// both patient and donor) are owned by the DonorPatientPair, not either
// person -- see app/models/donor_patient_pair.py. Bead specificity is a
// patient-only test (antibody screening against a bead panel; donors don't
// have one in this domain model — see AntibodyProfileEditor, which only
// ever appears on PatientDetailPage), so it resolves from the patient's
// archive instead.
export const PREFILL_SLOTS = [
  {
    slot: "hlaTypingReport",
    label: "HLA Typing Report",
    category: "hla_typing_report",
    source: "pair",
  },
  {
    slot: "crossmatchReport",
    label: "Crossmatch Report",
    category: "crossmatch_report",
    source: "pair",
  },
  {
    slot: "beadSpecificityPage1",
    label: "Bead Specificity Chart — Page 1",
    category: "bead_specificity_chart_page_1",
    source: "patient",
  },
  {
    slot: "beadSpecificityPage2",
    label: "Bead Specificity Chart — Page 2",
    category: "bead_specificity_chart_page_2",
    source: "patient",
  },
]

/**
 * pairFiles / patientFiles: arrays as returned by GET .../report-files
 * (each { id, category, original_filename, content_type, size_bytes, ... }).
 *
 * Returns one entry per wizard slot: `null` if nothing archived matches, or
 * `{ source: "pair" | "patient", reportFile }` naming which record's
 * archive it came from.
 */
export function resolvePrefillPhotos(pairFiles = [], patientFiles = []) {
  const result = {}

  for (const { slot, category, source } of PREFILL_SLOTS) {
    const files = source === "pair" ? pairFiles : patientFiles
    const match = files.find((f) => f.category === category)

    result[slot] = match ? { source, reportFile: match } : null
  }

  return result
}

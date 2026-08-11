// src/api/pairRegistration.js
import { createPair } from "./pairs"
import { uploadPairReportFile, uploadPatientReportFile } from "./reportFiles"

// Runs NewPairPage.jsx's full submission as a sequence of backend calls,
// same resumable shape as submitCompatibilityCheck in compatibilityWizard.js:
// pass back the `progress` object from a previous failed attempt (thrown
// errors carry it as `error.progress`) and any step already marked done
// (or any file slot that was empty to begin with) is skipped on retry --
// so a failed upload after a successful POST /pairs doesn't re-register
// the patient/donor.
//
// input: {
//   patient: PatientCreate-shaped payload (from PatientForm's onSubmit),
//   donor: DonorCreate-shaped payload (from DonorForm's onSubmit),
//   patientHla, donorHla: HLATypingEntry[] (from HlaTypingEditor's onSave),
//   crossmatch: PairCrossmatchInput-shaped object | null,
//   ocrVerified: { details, hla_typing } | null,
//   files: { hlaTypingReport, crossmatchReport, beadSpecificityPage1, beadSpecificityPage2 } (File | null),
// }
export async function submitPairRegistration(input, progress = {}, onStepComplete = () => {}) {
  const next = { ...progress }

  async function completeStep(patch) {
    Object.assign(next, patch)
    onStepComplete({ ...next })
  }

  try {
    if (!next.pairId) {
      const pair = await createPair({
        patient: input.patient,
        donor: input.donor,
        patient_hla: input.patientHla,
        donor_hla: input.donorHla,
        crossmatch: input.crossmatch,
        ocr_verified: input.ocrVerified,
      })
      await completeStep({ pairId: pair.id, patientId: pair.patient_id, donorId: pair.donor_id })
    }

    if (input.files.hlaTypingReport && !next.hlaTypingFileUploaded) {
      await uploadPairReportFile(next.pairId, "hla_typing_report", input.files.hlaTypingReport)
      await completeStep({ hlaTypingFileUploaded: true })
    }

    if (input.files.crossmatchReport && !next.crossmatchFileUploaded) {
      await uploadPairReportFile(next.pairId, "crossmatch_report", input.files.crossmatchReport)
      await completeStep({ crossmatchFileUploaded: true })
    }

    if (input.files.beadSpecificityPage1 && !next.beadPage1Uploaded) {
      await uploadPatientReportFile(
        next.patientId,
        "bead_specificity_chart_page_1",
        input.files.beadSpecificityPage1
      )
      await completeStep({ beadPage1Uploaded: true })
    }

    if (input.files.beadSpecificityPage2 && !next.beadPage2Uploaded) {
      await uploadPatientReportFile(
        next.patientId,
        "bead_specificity_chart_page_2",
        input.files.beadSpecificityPage2
      )
      await completeStep({ beadPage2Uploaded: true })
    }

    return next
  } catch (err) {
    // Attach whatever progress *did* succeed before the failure, so the
    // caller can store it and resume on retry instead of starting over.
    err.progress = next
    throw err
  }
}

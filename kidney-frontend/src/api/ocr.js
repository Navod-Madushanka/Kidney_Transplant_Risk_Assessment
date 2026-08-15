// src/api/ocr.js
import { apiGet, apiPostForm, ApiError } from "./client"

// Must match kidney-backend's Settings.ocr_upload_max_size_mb (app/core/
// config.py) -- this is only for the error message below, the backend is
// what actually enforces the cap. See that setting's docstring for why it
// has to stay equal to ocr-service's own cap too.
const UPLOAD_MAX_SIZE_MB = 15

// Maps wizard state's photo slot keys to the multipart field names the
// backend's /ocr/extract-batch/jobs endpoint expects (see kidney-backend's
// app/api/ocr.py start_extract_batch_job signature).
const SLOT_TO_FIELD = {
  hlaTypingReport: "hla_typing_report",
  beadSpecificityPage1: "bead_specificity_page_1",
  beadSpecificityPage2: "bead_specificity_page_2",
  crossmatchReport: "crossmatch_report",
}

function buildFormData(photos) {
  const formData = new FormData()
  let hasAny = false

  for (const [slot, fieldName] of Object.entries(SLOT_TO_FIELD)) {
    const file = photos[slot]
    if (file) {
      formData.append(fieldName, file)
      hasAny = true
    }
  }

  return hasAny ? formData : null
}

// Kicks off extraction as a server-owned background job and returns
// immediately with a job_id, instead of holding one HTTP connection open
// for however long the whole batch takes (bead specificity pages alone
// run 1.5-3 min each). The job keeps running on kidney-backend regardless
// of whether the caller keeps polling, navigates elsewhere, or drops the
// connection entirely — see getExtractionJob below, and
// WizardProvider.jsx's polling effect, which is what actually drives this
// from the wizard.
//
// patientId -- only NewPairPage.jsx's registration-time bead-specificity
// extraction passes this (the compatibility-check wizard's own Photos-step
// jobs start before a patient is even selected). Ties the job to that
// patient so it auto-saves its own results once done, unattended -- see
// kidney-backend's OcrExtractionJob.patient_id docstring.
export async function startExtractionJob(photos, patientId) {
  const formData = buildFormData(photos)
  if (!formData) {
    throw new Error("Upload at least one document before extracting.")
  }
  if (patientId) {
    formData.append("patient_id", patientId)
  }

  try {
    return await apiPostForm("/ocr/extract-batch/jobs", formData)
  } catch (err) {
    // A doctor who photographed a chart at full resolution needs to know
    // to retake it smaller, not that "something went wrong" -- the
    // generic extraction-failed path (see PhotoUploadsStep.jsx) doesn't
    // say that, so a 413 gets its own message naming the actual limit.
    if (err instanceof ApiError && err.status === 413) {
      throw new ApiError(
        `This image is larger than the ${UPLOAD_MAX_SIZE_MB} MB limit. Please retake it at a lower resolution and try again.`,
        err.status,
        err.data
      )
    }
    throw err
  }
}

// One snapshot of a job's current state: { job_id, status, documents, error }.
// `documents` is keyed by the same document_type strings SLOT_TO_FIELD's
// values use (e.g. "bead_specificity_page_1") -> { status, completed,
// total, ...whatever that document's extraction has produced so far }.
export function getExtractionJob(jobId) {
  return apiGet(`/ocr/extract-batch/jobs/${jobId}`)
}

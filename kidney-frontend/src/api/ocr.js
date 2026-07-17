// src/api/ocr.js
import { apiPostForm } from "./client"

// Maps wizard state's photo slot keys to the multipart field names the
// backend's /ocr/extract-batch endpoint expects (see kidney-backend's
// app/api/ocr.py extract_batch signature).
const SLOT_TO_FIELD = {
  hlaTypingReport: "hla_typing_report",
  beadSpecificityPage1: "bead_specificity_page_1",
  beadSpecificityPage2: "bead_specificity_page_2",
  crossmatchReport: "crossmatch_report",
}

export function extractLabDocuments(photos) {
  const formData = new FormData()
  let hasAny = false

  for (const [slot, fieldName] of Object.entries(SLOT_TO_FIELD)) {
    const file = photos[slot]
    if (file) {
      formData.append(fieldName, file)
      hasAny = true
    }
  }

  if (!hasAny) {
    return Promise.reject(new Error("Upload at least one document before extracting."))
  }

  return apiPostForm("/ocr/extract-batch", formData)
}
// src/utils/ocrHydrate.js
//
// Pure merge helpers for applying a normalizeOcrBatchResponse() payload
// onto existing form state, shared between wizardReducer.js's
// HYDRATE_FROM_OCR case and NewPairPage.jsx's local (non-reducer) OCR
// hydration -- both need the identical "don't blank out what's already
// there" semantics, so this is the one place that logic lives.

// Only overwrite a field if OCR actually found something -- never blank
// out a value the doctor already typed in by hand.
export function mergeDetails(existing, incoming) {
  const next = { ...existing }
  for (const [key, value] of Object.entries(incoming || {})) {
    if (value) next[key] = value
  }
  return next
}

// Matches incoming OCR rows to existing rows by locus (both sides use the
// same canonical HLA_LOCI codes), leaving any locus OCR didn't find
// untouched.
export function mergeHlaRows(existingRows, incomingRows) {
  if (!incomingRows || incomingRows.length === 0) return existingRows
  return existingRows.map((row) => {
    const match = incomingRows.find((r) => r.locus === row.locus)
    if (!match) return row
    return {
      ...row,
      allele_1: match.allele_1 || match.allele1 || row.allele_1,
      allele_2: match.allele_2 || match.allele2 || row.allele_2,
    }
  })
}

export function hasAnyValue(obj) {
  return Object.values(obj || {}).some((value) => value)
}

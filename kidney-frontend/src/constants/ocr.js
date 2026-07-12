// src/constants/ocr.js
//
// Mirrors the backend's LOW_CONFIDENCE_THRESHOLD constants (see
// paddleocr-service/hla_typing.py and paddleocr-service/mfi_extraction.py,
// both currently set to 0.75). Kept as a separate frontend constant rather
// than fetched from the backend, since it's small and stable — if the
// backend threshold ever changes, update both places in the same PR.
//
// Used by the compatibility-check wizard's review step to decide which
// OCR-extracted fields get a "needs review" warning icon.

export const OCR_LOW_CONFIDENCE_THRESHOLD = 0.75

// How many rows to show before collapsing a long OCR-extracted table
// (HLA typing, antibody profile) behind a "+ N more" expand control.
export const OCR_TABLE_PREVIEW_ROW_COUNT = 5
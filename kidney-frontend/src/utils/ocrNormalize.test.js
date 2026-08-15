// src/utils/ocrNormalize.test.js
import { describe, expect, it } from "vitest"
import { normalizeOcrBatchResponse, parseOcrMfi, parseOcrRhFactor } from "./ocrNormalize"

describe("parseOcrRhFactor", () => {
  it("reads a positive Rh off the same blood-type string parseOcrBloodType parses", () => {
    expect(parseOcrRhFactor("B Positive")).toBe("+")
  })

  it("reads a negative Rh off the same blood-type string parseOcrBloodType parses", () => {
    expect(parseOcrRhFactor("B Negative")).toBe("-")
  })

  it("handles the terse +/- form", () => {
    expect(parseOcrRhFactor("O+")).toBe("+")
  })

  it("returns an empty string when nothing is there to read", () => {
    expect(parseOcrRhFactor("")).toBe("")
  })
})

describe("parseOcrMfi", () => {
  it("passes through a real JSON number (the current backend contract)", () => {
    expect(parseOcrMfi(23706.91)).toBe(23706.91)
  })

  it("keeps a genuine MFI of 0 instead of treating it as missing", () => {
    // Regression test for a bug introduced by fixing the backend's mfi
    // str->float type: the old `if (!raw) return null` treated numeric 0
    // as falsy and silently dropped it, even though 0 is a common, real
    // value at the low end of a bead-specificity chart.
    expect(parseOcrMfi(0)).toBe(0)
  })

  it("returns null for a row the OCR couldn't read", () => {
    expect(parseOcrMfi(null)).toBeNull()
  })

  it("still handles a formatted string for backward compatibility", () => {
    expect(parseOcrMfi("23,706.91")).toBe(23706.91)
  })

  it("returns null for an empty string", () => {
    expect(parseOcrMfi("")).toBeNull()
  })
})

describe("normalizeOcrBatchResponse bead specificity", () => {
  it("keeps a zero-MFI row and a null-MFI row, but drops a row with no antigen at all", () => {
    // Part I (I8): a null MFI is the model flagging a row as illegible, not
    // the row being absent -- it must survive normalization so
    // BeadSpecificityStep can render its "couldn't read this value" marker.
    // Only a row with nothing to show (no antigen) is dropped here.
    const result = normalizeOcrBatchResponse({
      bead_specificity: [
        { antigen: "A23", mfi: 23706.91 },
        { antigen: "DQ4", mfi: 0 },
        { antigen: "DP1", mfi: null },
        { antigen: "", mfi: 500 },
      ],
    })

    expect(result.beadSpecificity).toEqual([
      { antigen: "A23", mfi: 23706.91, bead: null, page: null, panel: null, conflict: null },
      { antigen: "DQ4", mfi: 0, bead: null, page: null, panel: null, conflict: null },
      { antigen: "DP1", mfi: null, bead: null, page: null, panel: null, conflict: null },
    ])
  })

  it("carries bead, page, panel, and conflict through unchanged", () => {
    const result = normalizeOcrBatchResponse({
      bead_specificity: [
        {
          antigen: "A24",
          mfi: 950,
          bead: "011",
          page: 1,
          panel: "class_i",
          conflict: [950, 1200],
        },
      ],
    })

    expect(result.beadSpecificity).toEqual([
      { antigen: "A24", mfi: 950, bead: "011", page: 1, panel: "class_i", conflict: [950, 1200] },
    ])
  })
})

// src/utils/resolvePrefillPhotos.test.js
import { describe, expect, it } from "vitest"
import { resolvePrefillPhotos } from "./resolvePrefillPhotos"

function reportFile(category, overrides = {}) {
  return {
    id: `${category}-id`,
    category,
    original_filename: `${category}.pdf`,
    content_type: "application/pdf",
    size_bytes: 1024,
    created_at: "2026-08-01T00:00:00Z",
    ...overrides,
  }
}

describe("resolvePrefillPhotos", () => {
  it("returns null for every slot when neither record has any archived files", () => {
    const result = resolvePrefillPhotos([], [])

    expect(result).toEqual({
      hlaTypingReport: null,
      crossmatchReport: null,
      beadSpecificityPage1: null,
      beadSpecificityPage2: null,
    })
  })

  it("prefers the patient's copy of the joint HLA typing report over the donor's", () => {
    const patientFile = reportFile("hla_typing_report", { id: "patient-copy" })
    const donorFile = reportFile("hla_typing_report", { id: "donor-copy" })

    const result = resolvePrefillPhotos([patientFile], [donorFile])

    expect(result.hlaTypingReport).toEqual({ source: "patient", reportFile: patientFile })
  })

  it("falls back to the donor's crossmatch report when the patient doesn't have one archived", () => {
    const donorFile = reportFile("crossmatch_report")

    const result = resolvePrefillPhotos([], [donorFile])

    expect(result.crossmatchReport).toEqual({ source: "donor", reportFile: donorFile })
  })

  it("never falls back to the donor's archive for bead specificity pages", () => {
    const donorBeadChart = reportFile("bead_specificity_chart_page_1")

    const result = resolvePrefillPhotos([], [donorBeadChart])

    expect(result.beadSpecificityPage1).toBeNull()
  })

  it("resolves both bead specificity pages independently from the patient's archive", () => {
    const page1 = reportFile("bead_specificity_chart_page_1")
    const page2 = reportFile("bead_specificity_chart_page_2")

    const result = resolvePrefillPhotos([page1, page2], [])

    expect(result.beadSpecificityPage1).toEqual({ source: "patient", reportFile: page1 })
    expect(result.beadSpecificityPage2).toEqual({ source: "patient", reportFile: page2 })
  })

  it("ignores an 'other' category file entirely -- it doesn't map to any wizard slot", () => {
    const result = resolvePrefillPhotos([reportFile("other")], [])

    expect(Object.values(result).every((entry) => entry === null)).toBe(true)
  })
})

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
  it("returns null for every slot when neither the pair nor the patient has any archived files", () => {
    const result = resolvePrefillPhotos([], [])

    expect(result).toEqual({
      hlaTypingReport: null,
      crossmatchReport: null,
      beadSpecificityPage1: null,
      beadSpecificityPage2: null,
    })
  })

  it("resolves the joint HLA typing report from the pair's archive", () => {
    const pairFile = reportFile("hla_typing_report")

    const result = resolvePrefillPhotos([pairFile], [])

    expect(result.hlaTypingReport).toEqual({ source: "pair", reportFile: pairFile })
  })

  it("resolves the crossmatch report from the pair's archive", () => {
    const pairFile = reportFile("crossmatch_report")

    const result = resolvePrefillPhotos([pairFile], [])

    expect(result.crossmatchReport).toEqual({ source: "pair", reportFile: pairFile })
  })

  it("does not resolve a joint document from the patient's archive, even if present there", () => {
    const patientFile = reportFile("hla_typing_report")

    const result = resolvePrefillPhotos([], [patientFile])

    expect(result.hlaTypingReport).toBeNull()
  })

  it("resolves both bead specificity pages independently from the patient's archive", () => {
    const page1 = reportFile("bead_specificity_chart_page_1")
    const page2 = reportFile("bead_specificity_chart_page_2")

    const result = resolvePrefillPhotos([], [page1, page2])

    expect(result.beadSpecificityPage1).toEqual({ source: "patient", reportFile: page1 })
    expect(result.beadSpecificityPage2).toEqual({ source: "patient", reportFile: page2 })
  })

  it("does not resolve a bead specificity page from the pair's archive, even if present there", () => {
    const pairBeadChart = reportFile("bead_specificity_chart_page_1")

    const result = resolvePrefillPhotos([pairBeadChart], [])

    expect(result.beadSpecificityPage1).toBeNull()
  })

  it("ignores an 'other' category file entirely -- it doesn't map to any wizard slot", () => {
    const result = resolvePrefillPhotos([reportFile("other")], [reportFile("other")])

    expect(Object.values(result).every((entry) => entry === null)).toBe(true)
  })
})

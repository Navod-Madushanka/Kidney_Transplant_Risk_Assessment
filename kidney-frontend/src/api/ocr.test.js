// src/api/ocr.test.js
import { describe, expect, it, vi } from "vitest"
import { ApiError } from "./client"
import { startExtractionJob } from "./ocr"

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, apiPostForm: vi.fn() }
})

// Imported after the mock above so this binding is the mocked fn.
import { apiPostForm } from "./client"

describe("startExtractionJob", () => {
  it("rejects before making a request when no photo was attached", async () => {
    await expect(startExtractionJob({})).rejects.toThrow(
      "Upload at least one document before extracting."
    )
    expect(apiPostForm).not.toHaveBeenCalled()
  })

  it("resolves with the job id on success", async () => {
    apiPostForm.mockResolvedValue({ job_id: "job-1" })
    const file = new File(["x"], "hla.jpg", { type: "image/jpeg" })

    const result = await startExtractionJob({ hlaTypingReport: file })

    expect(result).toEqual({ job_id: "job-1" })
  })

  it("turns a 413 into a message naming the actual size limit", async () => {
    // Part G bounded-memory pass: kidney-backend now rejects an oversized
    // upload with a 413 instead of buffering it -- a doctor who
    // photographed a chart at full resolution needs to be told to retake
    // it smaller, not shown a generic "extraction failed" message.
    apiPostForm.mockRejectedValue(new ApiError("hla_typing_report exceeds the 15MB limit.", 413))
    const file = new File(["x"], "hla.jpg", { type: "image/jpeg" })

    await expect(startExtractionJob({ hlaTypingReport: file })).rejects.toThrow(
      "This image is larger than the 15 MB limit."
    )
  })

  it("leaves a non-413 failure message untouched", async () => {
    apiPostForm.mockRejectedValue(new ApiError("OCR service unavailable", 503))
    const file = new File(["x"], "hla.jpg", { type: "image/jpeg" })

    await expect(startExtractionJob({ hlaTypingReport: file })).rejects.toThrow(
      "OCR service unavailable"
    )
  })
})

// src/hooks/useExtractionJobPolling.js
import { useEffect, useRef } from "react"
import { getExtractionJob } from "../api/ocr"
import { normalizeOcrBatchResponse } from "../utils/ocrNormalize"
import { WIZARD_ACTIONS } from "../context/wizardReducer"

const POLL_INTERVAL_MS = 2500

// Drives an in-progress extraction job to completion independent of
// whichever wizard step is currently mounted -- called from WizardProvider
// (not PhotoUploadsStep) specifically so navigating away from Photos mid-
// extraction doesn't stop this from running; the job itself already keeps
// going server-side regardless, but without this living above any one step
// component, nothing would ever apply its results to the wizard's fields
// or progress list unless the doctor happened to still be on Photos when
// it finished.
//
// Polls GET /ocr/extract-batch/jobs/{id} on a timer while status is
// "running" (re-scheduling itself only after each poll resolves, so a slow
// response can't pile up overlapping requests), dispatching
// HYDRATE_FROM_OCR the moment each document flips to "done" -- tracked via
// hydratedDocTypesRef so a document is only merged into the wizard's real
// fields once, not on every subsequent poll tick, since each poll response
// is a full snapshot rather than a delta. Stops polling once the job
// reaches a terminal status (done/failed).
export function useExtractionJobPolling(dispatch, jobId, status) {
  const hydratedDocTypesRef = useRef(new Set())

  useEffect(() => {
    hydratedDocTypesRef.current = new Set()
  }, [jobId])

  useEffect(() => {
    if (!jobId || status !== "running") return

    let cancelled = false
    let timeoutId

    async function poll() {
      let job
      try {
        job = await getExtractionJob(jobId)
      } catch {
        // Transient network hiccup while polling -- retry on the next
        // tick rather than treating one failed poll as the job failing;
        // the job keeps running server-side regardless of whether polling
        // succeeds.
        if (!cancelled) timeoutId = setTimeout(poll, POLL_INTERVAL_MS)
        return
      }
      if (cancelled) return

      for (const [documentType, doc] of Object.entries(job.documents || {})) {
        if (doc.status === "done" && !hydratedDocTypesRef.current.has(documentType)) {
          hydratedDocTypesRef.current.add(documentType)
          dispatch({
            type: WIZARD_ACTIONS.HYDRATE_FROM_OCR,
            payload: normalizeOcrBatchResponse(doc),
          })
        }
      }

      dispatch({
        type: WIZARD_ACTIONS.SET_EXTRACTION_JOB_STATUS,
        status: job.status,
        documents: job.documents || {},
      })

      if (!cancelled && job.status === "running") {
        timeoutId = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    poll()

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [dispatch, jobId, status])
}

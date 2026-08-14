// src/hooks/useExtractionJobPolling.js
import { useEffect, useRef } from "react"
import { getExtractionJob } from "../api/ocr"
import { normalizeOcrBatchResponse } from "../utils/ocrNormalize"

const POLL_INTERVAL_MS = 2500

// Drives an in-progress extraction job to completion independent of
// whichever component mounted it -- e.g. WizardProvider keeps this running
// above any one wizard step so navigating away from Photos mid-extraction
// doesn't stop it; the job itself already keeps going server-side
// regardless, but without this living above the step component, nothing
// would ever apply its results anywhere unless the doctor happened to
// still be on that step when it finished. NewPairPage.jsx (a single page,
// not a wizard step) is a second, independent caller with its own local
// state instead of a wizard dispatch -- see onDocumentDone/onStatusChange
// below, which is what makes that possible without a second copy of this
// hook.
//
// Polls GET /ocr/extract-batch/jobs/{id} on a timer while status is
// "running" (re-scheduling itself only after each poll resolves, so a slow
// response can't pile up overlapping requests), calling onDocumentDone the
// moment each document flips to "done" -- tracked via hydratedDocTypesRef
// so a document is only reported once, not on every subsequent poll tick,
// since each poll response is a full snapshot rather than a delta. Stops
// polling once the job reaches a terminal status (done/failed).
export function useExtractionJobPolling({ jobId, status, onDocumentDone, onStatusChange }) {
  const hydratedDocTypesRef = useRef(new Set())

  // Callbacks are read via a ref, not the effect's dependency array: both
  // callers (WizardProvider, NewPairPage) pass fresh closures on every
  // render, and depending on them directly would tear down and restart the
  // poll loop (and its setTimeout chain) on every render instead of only
  // when jobId/status actually change.
  const callbacksRef = useRef({ onDocumentDone, onStatusChange })
  callbacksRef.current = { onDocumentDone, onStatusChange }

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
          callbacksRef.current.onDocumentDone?.(documentType, normalizeOcrBatchResponse(doc))
        }
      }

      // Third arg (the job's own backend-reported failure message, distinct
      // from a poll request itself failing -- see the catch block above) is
      // new and additive: existing callers (WizardProvider, NewPairPage)
      // only destructure the first two params, so this doesn't change their
      // behavior; BackgroundJobsProvider.jsx is the first caller that reads
      // it, to show a real failure reason in its toast.
      callbacksRef.current.onStatusChange?.(job.status, job.documents || {}, job.error ?? null)

      if (!cancelled && job.status === "running") {
        timeoutId = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    poll()

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [jobId, status])
}

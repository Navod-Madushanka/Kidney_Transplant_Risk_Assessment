// src/hooks/useExtractionJobPolling.js
import { useEffect, useRef } from "react"
import { getExtractionJob } from "../api/ocr"
import { normalizeOcrBatchResponse } from "../utils/ocrNormalize"

const POLL_INTERVAL_MS = 2500
// Part H fix: a failed poll used to retry on the same fixed 2.5s cadence
// forever, with no backoff and no signal to the doctor. Under real load
// (e.g. kidney-backend's connection pool exhausted -- see
// ocr_job_service.run_extraction_job's docstring) every client polling a
// dying backend at a fixed interval amplifies the pressure instead of
// relieving it, turning a transient squeeze into a stampede. Backing off
// gives the backend room to recover instead of being hammered by every
// open tab at once.
const MAX_BACKOFF_MS = 30000
// After this many consecutive failed polls, tell the caller polling looks
// stalled (see onPollingStalled below) rather than leaving the doctor
// staring at a frozen progress bar with no explanation. The job is very
// likely still running server-side -- BackgroundTasks/the job row don't
// stop just because polling can't currently reach them -- so this must
// never mark the job itself failed; that would push the doctor toward
// re-uploading and starting a second five-minute job for no reason.
const STALLED_AFTER_FAILURES = 4

function backoffDelayMs(consecutiveFailures) {
  if (consecutiveFailures <= 0) return POLL_INTERVAL_MS
  return Math.min(POLL_INTERVAL_MS * 2 ** consecutiveFailures, MAX_BACKOFF_MS)
}

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
//
// onPollingStalled(isStalled) -- optional. Fires (only on a transition, not
// every tick) once STALLED_AFTER_FAILURES consecutive polls have failed,
// and again with `false` the moment a poll succeeds. Distinct from the
// job's own status: this is about polling losing contact with the server,
// not the job failing.
export function useExtractionJobPolling({
  jobId,
  status,
  onDocumentDone,
  onStatusChange,
  onPollingStalled,
}) {
  const hydratedDocTypesRef = useRef(new Set())

  // Callbacks are read via a ref, not the effect's dependency array: both
  // callers (WizardProvider, NewPairPage) pass fresh closures on every
  // render, and depending on them directly would tear down and restart the
  // poll loop (and its setTimeout chain) on every render instead of only
  // when jobId/status actually change. Updated from a no-deps effect
  // (runs after every commit) rather than during render itself, since
  // mutating a ref's `.current` during render is impure -- poll() only
  // ever reads this ref later, asynchronously, so a post-commit update is
  // just as fresh as a during-render one would have been.
  const callbacksRef = useRef({ onDocumentDone, onStatusChange, onPollingStalled })
  useEffect(() => {
    callbacksRef.current = { onDocumentDone, onStatusChange, onPollingStalled }
  })

  useEffect(() => {
    hydratedDocTypesRef.current = new Set()
  }, [jobId])

  useEffect(() => {
    if (!jobId || status !== "running") return

    let cancelled = false
    let timeoutId
    let consecutiveFailures = 0
    let isStalled = false

    async function poll() {
      let job
      try {
        job = await getExtractionJob(jobId)
      } catch {
        // Transient network hiccup while polling -- retry (with backoff)
        // rather than treating one failed poll as the job failing; the job
        // keeps running server-side regardless of whether polling
        // succeeds.
        consecutiveFailures += 1
        const nowStalled = consecutiveFailures >= STALLED_AFTER_FAILURES
        if (nowStalled !== isStalled) {
          isStalled = nowStalled
          callbacksRef.current.onPollingStalled?.(isStalled)
        }
        if (!cancelled) {
          timeoutId = setTimeout(poll, backoffDelayMs(consecutiveFailures))
        }
        return
      }
      if (cancelled) return

      if (consecutiveFailures > 0) {
        consecutiveFailures = 0
        if (isStalled) {
          isStalled = false
          callbacksRef.current.onPollingStalled?.(false)
        }
      }

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

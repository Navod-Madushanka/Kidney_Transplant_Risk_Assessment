// src/context/BackgroundJobsProvider.jsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { BackgroundJobsContext } from "./BackgroundJobsContext"
import { useExtractionJobPolling } from "../hooks/useExtractionJobPolling"
import BackgroundJobToast from "../components/domain/ocr/BackgroundJobToast"

const AUTO_DISMISS_MS = 8000

// Client-only synthetic id -- same convention as BeadSpecificityStep.jsx's
// nextRowId, since these ids never leave the browser (jobId, the real
// server-assigned id, is what's actually polled).
let nextJobId = 1

// Renders nothing -- exists purely so each background job gets its own
// useExtractionJobPolling instance (the hook polls exactly one job), while
// still satisfying React's rules of hooks: one component instance per array
// entry, keyed by job.id, rather than calling the hook in a loop.
function JobPoller({ job, onUpdate }) {
  useExtractionJobPolling({
    jobId: job.jobId,
    status: job.status,
    onDocumentDone: () => {},
    onStatusChange: (status, documents, error) => onUpdate({ status, documents, error }),
  })
  return null
}

/**
 * Tracks OCR extraction jobs kicked off outside the compatibility-check
 * wizard (today: registration-time bead-specificity extraction -- see
 * NewPairPage.jsx) so a doctor can navigate anywhere in the app and still
 * see a small progress notification, instead of losing all visibility the
 * moment they leave the page that started it. Mounted once above every
 * authenticated route (see App.jsx) -- unlike WizardProvider, which resets
 * per wizard session and only exists inside /checks/new/*.
 *
 * Survives in-app navigation only, not a full page refresh (jobs live in
 * plain React state here, not persisted storage) -- same tradeoff the
 * wizard's own extraction state already makes, see
 * ocr_extraction_background_job's project memory.
 */
export function BackgroundJobsProvider({ children }) {
  const [jobs, setJobs] = useState([])
  const dismissTimersRef = useRef({})

  const dismissJob = useCallback((id) => {
    clearTimeout(dismissTimersRef.current[id])
    delete dismissTimersRef.current[id]
    setJobs((prev) => prev.filter((job) => job.id !== id))
  }, [])

  const startJob = useCallback(({ jobId, label, documentSlots }) => {
    // Guards against the same server-side job getting tracked (and polled)
    // twice -- e.g. a doctor double-clicking Register before the first
    // click's request resolves would otherwise register the same jobId
    // twice, each with its own JobPoller polling it independently at 2x
    // the intended rate. See useExtractionJobPolling.js's docstring on why
    // hammering a possibly-struggling backend is exactly the wrong
    // response to that backend struggling.
    setJobs((prev) => {
      if (prev.some((job) => job.jobId === jobId)) return prev
      const id = nextJobId++
      return [
        ...prev,
        { id, jobId, label, documentSlots, status: "running", documents: {}, error: null },
      ]
    })
  }, [])

  const updateJob = useCallback((id, patch) => {
    setJobs((prev) => prev.map((job) => (job.id === id ? { ...job, ...patch } : job)))
  }, [])

  // Schedules auto-dismiss the moment a job reaches a terminal status --
  // watched here via effect (not inside updateJob's setState updater, which
  // must stay pure) so each job is only ever scheduled once, guarded by
  // dismissTimersRef rather than relying on this effect firing exactly once
  // per transition.
  useEffect(() => {
    for (const job of jobs) {
      const isTerminal = job.status === "done" || job.status === "failed"
      if (isTerminal && !dismissTimersRef.current[job.id]) {
        dismissTimersRef.current[job.id] = setTimeout(() => dismissJob(job.id), AUTO_DISMISS_MS)
      }
    }
  }, [jobs, dismissJob])

  useEffect(() => {
    const timers = dismissTimersRef.current
    return () => {
      Object.values(timers).forEach(clearTimeout)
    }
  }, [])

  const value = useMemo(() => ({ jobs, startJob, dismissJob }), [jobs, startJob, dismissJob])

  return (
    <BackgroundJobsContext.Provider value={value}>
      {children}
      {jobs.map((job) => (
        <JobPoller key={job.id} job={job} onUpdate={(patch) => updateJob(job.id, patch)} />
      ))}
      <BackgroundJobToast jobs={jobs} onDismiss={dismissJob} />
    </BackgroundJobsContext.Provider>
  )
}

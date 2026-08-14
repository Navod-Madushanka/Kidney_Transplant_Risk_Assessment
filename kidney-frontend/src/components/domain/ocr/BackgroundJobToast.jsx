// src/components/domain/ocr/BackgroundJobToast.jsx
import ExtractionProgressList from "./ExtractionProgressList"

/**
 * Small floating stack of cards, one per active BackgroundJobsProvider job
 * -- fixed-position so it stays visible regardless of which route is
 * mounted underneath it (see BackgroundJobsProvider's docstring for why
 * this needs to be app-wide rather than page-scoped). Reuses
 * ExtractionProgressList as-is for the per-document bars, same component
 * PhotoUploadsStep/NewPairPage already use inline.
 */
export default function BackgroundJobToast({ jobs, onDismiss }) {
  if (jobs.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-[calc(100vw-2rem)] sm:w-80">
      {jobs.map((job) => {
        const isRunning = job.status === "running"
        const isDone = job.status === "done"
        const isFailed = job.status === "failed"

        return (
          <div
            key={job.id}
            role="status"
            className="bg-surface border border-border rounded-lg shadow-card p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <p className="text-[13px] font-semibold text-text leading-tight">{job.label}</p>
              <button
                type="button"
                onClick={() => onDismiss(job.id)}
                aria-label="Dismiss"
                className="text-text-muted hover:text-text shrink-0 leading-none"
              >
                ✕
              </button>
            </div>

            {isRunning && (
              <p className="text-[12px] text-text-muted mt-1">
                Reading in the background — you can keep working elsewhere.
              </p>
            )}
            {isDone && (
              <p className="text-[12px] text-clear font-medium mt-1">
                ✓ Done — review it next time you use this patient's data.
              </p>
            )}
            {isFailed && (
              <p className="text-[12px] text-high-risk font-medium mt-1">
                {job.error || "Extraction failed."}
              </p>
            )}

            {Object.keys(job.documents).length > 0 && (
              <ExtractionProgressList
                documentSlots={job.documentSlots}
                extractionDocuments={job.documents}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

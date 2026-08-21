// src/components/domain/ocr/ExtractionProgressList.jsx
//
// Per-document progress rows for a running/completed OCR extraction job
// (see useExtractionJobPolling.js) -- originally PhotoUploadsStep.jsx's own
// markup, lifted out so NewPairPage.jsx (a second, independent caller of
// the same polling hook) doesn't need a hand-copied second implementation.

// Backend document_type tag -> friendly label, decoupled from whatever
// label a caller's own upload slot uses.
const DOCUMENT_TYPE_LABELS = {
  hla_typing_report: "HLA typing report",
  crossmatch_report: "Crossmatch report",
  bead_specificity_page_1: "Bead specificity chart — page 1",
  bead_specificity_page_2: "Bead specificity chart — page 2",
}

/**
 * documentSlots: [{ documentType, label }] -- the set of documents this
 * caller might extract (PhotoUploadsStep's UPLOAD_SLOTS, or NewPairPage's
 * two-slot subset).
 * extractionDocuments: state.extraction.documents shape from the wizard
 * reducer / NewPairPage's local state -- keyed by documentType.
 */
export default function ExtractionProgressList({ documentSlots, extractionDocuments }) {
  const activeSlots = documentSlots.filter(({ documentType }) => extractionDocuments[documentType])
  if (activeSlots.length === 0) return null

  // Without this, a bar sitting at 1/8 for a couple of minutes reads as
  // stuck rather than normal -- see api/ocr.js's startExtractionJob comment
  // for where the 1.5-3 min/page figure comes from. Shown whenever anything
  // is still in flight, not just once at the top, since that's the moment a
  // viewer is actually watching the bar and wondering.
  const stillRunning = activeSlots.some(({ documentType }) => {
    const status = extractionDocuments[documentType]?.status
    return status && status !== "done"
  })

  return (
    <ul className="mt-3 flex flex-col gap-2.5">
      {stillRunning && (
        <li className="text-[12px] text-text-muted -mb-1">
          This usually takes 2–3 minutes per page — a bar sitting still for a while is normal.
        </li>
      )}
      {activeSlots.map(({ documentType, label }) => {
        const progress = extractionDocuments[documentType]
        const isDone = progress.status === "done"
        // Bead specificity's 8 tiles give a real percentage; HLA
        // typing/crossmatch (total: 1) have no intermediate signal — an
        // in-progress bar for those would just be a static, misleading
        // number, so it pulses instead of claiming a %.
        const isIndeterminate = progress.status === "in_progress" && progress.total <= 1
        const percent = isDone
          ? 100
          : Math.round((progress.completed / Math.max(progress.total, 1)) * 100)
        const displayLabel = DOCUMENT_TYPE_LABELS[documentType] || label

        let statusText = "Waiting…"
        if (isDone) statusText = "100%"
        else if (isIndeterminate) statusText = "Reading…"
        else if (progress.status === "in_progress")
          statusText = `${progress.completed}/${progress.total} sections — ${percent}%`

        return (
          <li key={documentType} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2">
              <span className={`text-[13px] ${isDone ? "text-clear font-medium" : "text-text"}`}>
                {isDone ? "✓ " : ""}
                {displayLabel}
              </span>
              <span className="text-[12px] text-text-muted tabular-nums shrink-0">{statusText}</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-border overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  isDone ? "bg-clear" : "bg-accent"
                } ${isIndeterminate ? "animate-pulse" : ""}`}
                style={{ width: `${isIndeterminate ? 40 : percent}%` }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

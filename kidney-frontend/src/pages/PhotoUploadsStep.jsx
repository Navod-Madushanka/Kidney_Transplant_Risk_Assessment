// src/pages/wizard/PhotoUploadsStep.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "@/hooks/useWizard"
import { startExtractionJob } from "@/api/ocr"
import FileUpload from "@/components/ui/FileUpload"
import Button from "@/components/ui/Button"
import Card from "@/components/ui/Card"

const UPLOAD_SLOTS = [
  {
    slot: "hlaTypingReport",
    documentType: "hla_typing_report",
    label: "HLA Typing Report",
    helperText: "The joint patient + donor histocompatibility type-match report",
  },
  {
    slot: "beadSpecificityPage1",
    documentType: "bead_specificity_page_1",
    label: "Bead Specificity Chart — Page 1",
    helperText: "First page of the patient's antibody bead specificity chart",
  },
  {
    slot: "beadSpecificityPage2",
    documentType: "bead_specificity_page_2",
    label: "Bead Specificity Chart — Page 2",
    helperText: "Next page, if the chart continues (some reports run several pages)",
  },
  {
    slot: "crossmatchReport",
    documentType: "crossmatch_report",
    label: "Crossmatch Report",
    helperText: "T-cell / B-cell crossmatch result, if available yet",
  },
]

// Bead specificity pages take 1.5-3 min each (8 sequential vision-model
// calls per page) while HLA typing/crossmatch finish in seconds — extraction
// runs as a background job on kidney-backend (see
// useExtractionJobPolling.js) that keeps going and reports progress
// regardless of which wizard step is open, so this maps the backend's
// document_type tag to a friendly label for the running progress list.
const DOCUMENT_TYPE_LABELS = {
  hla_typing_report: "HLA typing report",
  crossmatch_report: "Crossmatch report",
  bead_specificity_page_1: "Bead specificity chart — page 1",
  bead_specificity_page_2: "Bead specificity chart — page 2",
}

export default function PhotoUploadsStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  // Only for "couldn't even start the job" (the POST itself failed) --
  // everything about the job ONCE it exists (progress, per-document
  // errors, done/failed) lives in state.extraction instead of here, so it
  // survives navigating to another wizard step and back. See
  // wizardReducer.js's buildInitialWizardState and
  // useExtractionJobPolling.js.
  const [startError, setStartError] = useState("")

  const { status: extractionStatus, documents: extractionDocuments } = state.extraction
  const isExtracting = extractionStatus === "running"
  const isExtractionDone = extractionStatus === "done"
  const hasAnyPhoto = Object.values(state.photos).some(Boolean)
  const warnings = Object.values(extractionDocuments).flatMap((doc) => doc.errors || [])

  function handleContinue() {
    actions.unlockStep(2)
    navigate("/checks/new/details")
  }

  async function handleExtract() {
    setStartError("")

    const documentTypes = UPLOAD_SLOTS.filter(({ slot }) => state.photos[slot]).map(
      ({ documentType }) => documentType
    )

    try {
      const { job_id } = await startExtractionJob(state.photos)
      actions.startExtractionJob(job_id, documentTypes)
    } catch (err) {
      setStartError(err.message || "Couldn't start extraction. Please try again.")
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Upload documents</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Add whatever you have on hand, then tap Extract to auto-fill the next steps. Everything
          here is optional, and you can come back to add more later. Extraction keeps running in
          the background even if you move on to the next step.
        </p>
      </div>

      <Card>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {UPLOAD_SLOTS.map(({ slot, label, helperText }) => (
            <FileUpload
              key={slot}
              label={label}
              helperText={helperText}
              accept="image/*,application/pdf"
              initialFile={state.photos[slot]}
              onFileSelect={(file) => actions.setPhoto(slot, file)}
            />
          ))}
        </div>

        <div className="flex items-center gap-3 mt-5">
          <Button
            type="button"
            variant="secondary"
            loading={isExtracting}
            disabled={!hasAnyPhoto || isExtracting}
            onClick={handleExtract}
          >
            {isExtracting ? "Reading documents…" : "Extract from documents"}
          </Button>
          {isExtractionDone && !startError && (
            <span className="text-[13px] text-clear font-medium">
              Extracted — review the details in the next steps
            </span>
          )}
        </div>

        {Object.keys(extractionDocuments).length > 0 && !isExtractionDone && (
          <ul className="mt-3 flex flex-col gap-2.5">
            {UPLOAD_SLOTS.filter(({ documentType }) => extractionDocuments[documentType]).map(
              ({ documentType, label }) => {
                const progress = extractionDocuments[documentType]
                const isDone = progress.status === "done"
                // Bead specificity's 8 tiles give a real percentage; HLA
                // typing/crossmatch (total: 1) have no intermediate signal
                // — an in-progress bar for those would just be a static,
                // misleading number, so it pulses instead of claiming a %.
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
                      <span
                        className={`text-[13px] ${
                          isDone ? "text-clear font-medium" : "text-text"
                        }`}
                      >
                        {isDone ? "✓ " : ""}
                        {displayLabel}
                      </span>
                      <span className="text-[12px] text-text-muted tabular-nums shrink-0">
                        {statusText}
                      </span>
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
              }
            )}
          </ul>
        )}

        {(startError || (extractionStatus === "failed" && state.extraction.error)) && (
          <p className="text-[13px] text-high-risk font-medium mt-3">
            {startError || state.extraction.error}
          </p>
        )}

        {warnings.length > 0 && (
          <div className="rounded-md bg-moderate-subtle border border-moderate/30 p-3 mt-3">
            <p className="text-[13px] font-semibold text-text">Some fields need a second look</p>
            <ul className="mt-1 flex flex-col gap-0.5">
              {warnings.map((warning, index) => (
                <li key={index} className="text-[13px] text-text-muted">
                  {warning.field}: {warning.message || "couldn't read this clearly — check it manually in the next steps"}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <div className="flex items-center justify-between">
        <Button variant="secondary" onClick={() => navigate("/checks/new/subject")}>
          Back
        </Button>
        <Button size="lg" onClick={handleContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}

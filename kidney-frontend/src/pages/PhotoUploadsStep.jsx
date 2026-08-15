// src/pages/wizard/PhotoUploadsStep.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "@/hooks/useWizard"
import { startExtractionJob } from "@/api/ocr"
import FileUpload from "@/components/ui/FileUpload"
import Button from "@/components/ui/Button"
import Card from "@/components/ui/Card"
import ExtractionProgressList from "@/components/domain/ocr/ExtractionProgressList"

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
    actions.unlockStep(1)
    navigate("/checks/new/subject")
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
          <ExtractionProgressList
            documentSlots={UPLOAD_SLOTS}
            extractionDocuments={extractionDocuments}
          />
        )}

        {(startError || (extractionStatus === "failed" && state.extraction.error)) && (
          <p className="text-[13px] text-high-risk font-medium mt-3">
            {startError || state.extraction.error}
          </p>
        )}

        {isExtracting && state.extraction.pollingStalled && (
          <p className="text-[13px] text-moderate font-medium mt-3">
            Lost contact with the server — still trying. The extraction is very likely still
            running; no need to re-upload.
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

      <div className="flex justify-end">
        <Button size="lg" onClick={handleContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}

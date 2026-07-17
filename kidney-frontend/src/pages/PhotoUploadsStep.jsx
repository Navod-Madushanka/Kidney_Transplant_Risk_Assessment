// src/pages/wizard/PhotoUploadsStep.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "@/hooks/useWizard"
import { extractLabDocuments } from "@/api/ocr"
import { normalizeOcrBatchResponse } from "@/utils/ocrNormalize"
import FileUpload from "@/components/ui/FileUpload"
import Button from "@/components/ui/Button"
import Card from "@/components/ui/Card"

const UPLOAD_SLOTS = [
  {
    slot: "hlaTypingReport",
    label: "HLA Typing Report",
    helperText: "The joint patient + donor histocompatibility type-match report",
  },
  {
    slot: "beadSpecificityPage1",
    label: "Bead Specificity Chart — Page 1",
    helperText: "First page of the patient's antibody bead specificity chart",
  },
  {
    slot: "beadSpecificityPage2",
    label: "Bead Specificity Chart — Page 2",
    helperText: "Next page, if the chart continues (some reports run several pages)",
  },
  {
    slot: "crossmatchReport",
    label: "Crossmatch Report",
    helperText: "T-cell / B-cell crossmatch result, if available yet",
  },
]

export default function PhotoUploadsStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  const [isExtracting, setIsExtracting] = useState(false)
  const [extractError, setExtractError] = useState("")
  const [extractWarnings, setExtractWarnings] = useState([])
  const [extractedAt, setExtractedAt] = useState(null)

  const hasAnyPhoto = Object.values(state.photos).some(Boolean)

  function handleContinue() {
    actions.unlockStep(1)
    navigate("/checks/new/details")
  }

  async function handleExtract() {
    setExtractError("")
    setExtractWarnings([])
    setExtractedAt(null)
    setIsExtracting(true)

    try {
      const response = await extractLabDocuments(state.photos)
      const normalized = normalizeOcrBatchResponse(response)
      actions.hydrateFromOcr(normalized)
      setExtractedAt(Date.now())
      if (response.errors?.length > 0) {
        setExtractWarnings(response.errors)
      }
    } catch (err) {
      setExtractError(err.message || "Couldn't read these documents. Please try again.")
    } finally {
      setIsExtracting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Upload documents</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Add whatever you have on hand, then tap Extract to auto-fill the next steps. Everything
          here is optional, and you can come back to add more later.
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
            disabled={!hasAnyPhoto}
            onClick={handleExtract}
          >
            {isExtracting ? "Reading documents…" : "Extract from documents"}
          </Button>
          {extractedAt && !extractError && (
            <span className="text-[13px] text-clear font-medium">
              Extracted — review the details in the next steps
            </span>
          )}
        </div>

        {extractError && (
          <p className="text-[13px] text-high-risk font-medium mt-3">{extractError}</p>
        )}

        {extractWarnings.length > 0 && (
          <div className="rounded-md bg-moderate-subtle border border-moderate/30 p-3 mt-3">
            <p className="text-[13px] font-semibold text-text">Some fields need a second look</p>
            <ul className="mt-1 flex flex-col gap-0.5">
              {extractWarnings.map((warning, index) => (
                <li key={index} className="text-[13px] text-text-muted">
                  {warning.field}: couldn't read this clearly — check it manually in the next steps
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
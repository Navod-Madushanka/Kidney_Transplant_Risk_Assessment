// src/pages/wizard/PhotoUploadsStep.jsx
import { useNavigate } from "react-router-dom"
import { useWizard } from "../../hooks/useWizard"
import FileUpload from "../../components/ui/FileUpload"
import Button from "../../components/ui/Button"
import Card from "../../components/ui/Card"

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

  function handleContinue() {
    actions.unlockStep(1)
    navigate("/checks/new/details")
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Upload documents</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Add whatever you have on hand — everything here is optional, and you can come
          back to add more later.
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
      </Card>

      <div className="flex justify-end">
        <Button size="lg" onClick={handleContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}
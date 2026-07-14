// src/pages/SensitizationStep.jsx
import { useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { SENSITIZATION_EVENT_OPTIONS } from "../constants/clinicalEnums"
import {
  SENSITIZATION_EVENT_WEIGHTS,
  SENSITIZATION_CUTOFF_REDUCTION_FACTOR,
} from "../constants/sensitizationWeights"
import Card from "../components/ui/Card"
import ToggleSwitch from "../components/ui/ToggleSwitch"
import InputField from "../components/ui/InputField"
import Button from "../components/ui/Button"

function formatPoints(points) {
  return `+${points.toFixed(1)} sensitization points`
}

export default function SensitizationStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  const sensitizationScore = SENSITIZATION_EVENT_OPTIONS.reduce((total, option) => {
    return state.sensitization[option.value]
      ? total + SENSITIZATION_EVENT_WEIGHTS[option.value]
      : total
  }, 0)

  const adjustedCutoff =
    state.mfi_cutoff - sensitizationScore * SENSITIZATION_CUTOFF_REDUCTION_FACTOR

  function handleMfiCutoffChange(e) {
    const raw = e.target.value
    actions.setMfiCutoff(raw === "" ? 0 : Number(raw))
  }

  function handleContinue() {
    actions.unlockStep(4)
    navigate("/checks/new/bead-chart")
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Sensitization &amp; MFI cutoff</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Prior sensitizing events lower the MFI threshold used to flag donor-specific
          antibodies — the more sensitized the patient, the more cautious the cutoff.
        </p>
      </div>

      <Card>
        <Card.Header
          title="Sensitizing events"
          subtitle="Toggle any that apply to this patient's history"
        />
        <div className="flex flex-col divide-y divide-border">
          {SENSITIZATION_EVENT_OPTIONS.map((option) => (
            <ToggleSwitch
              key={option.value}
              label={option.label}
              checked={state.sensitization[option.value]}
              onChange={(checked) =>
                actions.setSensitization({ [option.value]: checked })
              }
              helperText={formatPoints(SENSITIZATION_EVENT_WEIGHTS[option.value])}
              className="py-3 first:pt-0 last:pb-0"
            />
          ))}
        </div>
      </Card>

      <Card>
        <Card.Header title="MFI cutoff" subtitle="Baseline threshold before sensitization adjustment" />

        <InputField
          label="Base MFI cutoff"
          type="number"
          inputMode="numeric"
          value={state.mfi_cutoff}
          onChange={handleMfiCutoffChange}
          className="[&_input]:h-14 [&_input]:text-[22px] [&_input]:font-bold [&_label]:text-[15px]"
          helperText="Default is 2000 — adjust only if this lab uses a different baseline"
        />

        <div className="mt-5 rounded-md bg-bg border border-border p-4 flex items-center justify-between">
          <div>
            <p className="text-[13px] font-semibold text-text-muted">
              Sensitization score: {sensitizationScore.toFixed(1)} pts
            </p>
            <p className="text-[13px] text-text-muted mt-0.5">
              Adjusted cutoff used for the DSA check
            </p>
          </div>
          <p className="text-[26px] font-bold text-accent tabular-nums">
            {adjustedCutoff.toLocaleString()}
          </p>
        </div>
      </Card>

      <div className="flex items-center justify-between">
        <Button variant="secondary" onClick={() => navigate("/checks/new/hla")}>
          Back
        </Button>
        <Button size="lg" onClick={handleContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}
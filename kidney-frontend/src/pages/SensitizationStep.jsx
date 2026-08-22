// src/pages/SensitizationStep.jsx
import { useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { SENSITIZATION_EVENT_OPTIONS } from "../constants/clinicalEnums"
import { SENSITIZATION_EVENT_WEIGHTS } from "../constants/sensitizationWeights"
import Card from "../components/ui/Card"
import ToggleSwitch from "../components/ui/ToggleSwitch"
import InputField from "../components/ui/InputField"
import Button from "../components/ui/Button"

function formatPoints(points) {
  return `+${points.toFixed(1)} sensitisation points`
}

export default function SensitizationStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  const sensitizationScore = SENSITIZATION_EVENT_OPTIONS.reduce((total, option) => {
    return state.sensitization[option.value]
      ? total + SENSITIZATION_EVENT_WEIGHTS[option.value]
      : total
  }, 0)

  function handleToggle(eventType, checked) {
    actions.setSensitization({ [eventType]: checked })
    // Switching an event off clears its date too, so a stale date can't
    // silently linger and resurface if the doctor re-enables it later
    // expecting a blank field.
    if (!checked) {
      actions.setSensitizationDate(eventType, "")
    }
  }

  function handleContinue() {
    actions.unlockStep(5)
    navigate("/checks/new/bead-chart")
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Sensitising history (informational)</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Prior sensitising events are recorded for clinical reference on the compatibility
          report (Step 2) — they don't change the automated DSA antibody check, which uses its
          own fixed severity scale regardless of sensitisation history.
        </p>
      </div>

      <Card>
        <Card.Header
          title="Sensitising events"
          subtitle="Toggle any that apply, and enter when each one occurred"
        />
        <div className="flex flex-col divide-y divide-border">
          {SENSITIZATION_EVENT_OPTIONS.map((option) => {
            const isOn = state.sensitization[option.value]
            return (
              <div key={option.value} className="py-3 first:pt-0 last:pb-0 flex flex-col gap-3">
                <ToggleSwitch
                  label={option.label}
                  checked={isOn}
                  onChange={(checked) => handleToggle(option.value, checked)}
                  helperText={formatPoints(SENSITIZATION_EVENT_WEIGHTS[option.value])}
                />
                {isOn && (
                  <InputField
                    label={`Date of ${option.label.toLowerCase()}`}
                    type="date"
                    value={state.sensitization_dates[option.value]}
                    onChange={(e) => actions.setSensitizationDate(option.value, e.target.value)}
                    required
                    className="max-w-xs"
                  />
                )}
              </div>
            )
          })}
        </div>
      </Card>

      <div className="rounded-md bg-bg border border-border p-4 flex items-center justify-between">
        <div>
          <p className="text-[13px] font-semibold text-text-muted">
            Sensitisation score: {sensitizationScore.toFixed(1)} pts
          </p>
          <p className="text-[13px] text-text-muted mt-0.5">
            Reference only — shown on the compatibility report's Step 2, doesn't gate anything
          </p>
        </div>
      </div>

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
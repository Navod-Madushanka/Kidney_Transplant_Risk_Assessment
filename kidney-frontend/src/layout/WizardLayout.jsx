// src/layout/WizardLayout.jsx
import { Outlet, useLocation, useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { WIZARD_STEPS, wizardStepIndexForPath } from "../constants/wizardSteps"
import StepProgress from "../components/ui/StepProgress"

export default function WizardLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { state } = useWizard()

  // Current step is derived from the URL (last path segment), not local
  // state — so a refresh or a direct link to /checks/new/hla lands on the
  // right step in the progress indicator without extra bookkeeping.
  const currentSegment = location.pathname.split("/").pop()
  const currentIndex = wizardStepIndexForPath(currentSegment)

  function handleStepSelect(index) {
    navigate(`/checks/new/${WIZARD_STEPS[index].path}`)
  }

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <header className="sticky top-0 z-20 bg-surface border-b border-border px-4 py-4 sm:px-6">
        <div className="max-w-2xl mx-auto flex flex-col items-center gap-3">
          <div className="w-full flex items-center justify-between">
            <button
              type="button"
              onClick={() => navigate("/")}
              className="text-[13px] font-semibold text-text-muted hover:text-high-risk transition-colors"
            >
              Exit check
            </button>
            <span className="text-[13px] font-semibold text-text-muted">
              Step {currentIndex + 1} of {WIZARD_STEPS.length}
            </span>
          </div>

          <StepProgress
            steps={WIZARD_STEPS}
            currentIndex={currentIndex}
            furthestIndex={state.furthestStepIndex}
            onStepSelect={handleStepSelect}
            className="w-full"
          />
        </div>
      </header>

      <main className="flex-1 px-4 py-6 sm:px-6 pb-16">
        <div className="max-w-2xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
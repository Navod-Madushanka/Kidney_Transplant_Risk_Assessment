// src/components/ui/StepProgress.jsx

/**
 * The wizard's step indicator — numbered dots connected by a line, with the
 * current step's label shown below. Only steps at or before
 * furthestStepIndex are tappable, so a doctor can always go back to fix
 * something but can't skip ahead of data they haven't entered yet.
 *
 * Usage:
 *   <StepProgress
 *     steps={[
 *       { key: "photos", label: "Photos" },
 *       { key: "details", label: "Patient & Donor" },
 *       { key: "hla", label: "HLA Typing" },
 *       { key: "sensitization", label: "Sensitization" },
 *       { key: "bead-chart", label: "Bead Specificity" },
 *     ]}
 *     currentIndex={2}
 *     furthestIndex={3}
 *     onStepSelect={(index) => navigate(steps[index].path)}
 *   />
 */
export default function StepProgress({
  steps = [],
  currentIndex = 0,
  furthestIndex = 0,
  onStepSelect,
  className = "",
}) {
  const currentLabel = steps[currentIndex]?.label

  return (
    <div className={["flex flex-col items-center gap-2", className].join(" ")}>
      <ol className="flex items-center w-full max-w-md">
        {steps.map((step, index) => {
          const isComplete = index < currentIndex
          const isCurrent = index === currentIndex
          const isReachable = index <= furthestIndex
          const isLast = index === steps.length - 1

          return (
            <li key={step.key} className="flex items-center flex-1 last:flex-none">
              <button
                type="button"
                disabled={!isReachable}
                aria-current={isCurrent ? "step" : undefined}
                aria-label={step.label}
                onClick={() => isReachable && onStepSelect?.(index)}
                className={[
                  "flex items-center justify-center h-7 w-7 shrink-0 rounded-full text-[12px] font-bold",
                  "transition-colors duration-150",
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                  isReachable ? "cursor-pointer" : "cursor-not-allowed",
                  isComplete
                    ? "bg-accent text-white"
                    : isCurrent
                    ? "bg-accent text-white ring-4 ring-accent-subtle"
                    : "bg-bg text-text-muted border border-border",
                ].join(" ")}
              >
                {isComplete ? (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <path
                      d="M4 10.5L8 14.5L16 6"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  index + 1
                )}
              </button>

              {!isLast && (
                <span
                  aria-hidden="true"
                  className={[
                    "flex-1 h-[2px] mx-1.5",
                    isComplete ? "bg-accent" : "bg-border",
                  ].join(" ")}
                />
              )}
            </li>
          )
        })}
      </ol>

      {currentLabel && (
        <p className="text-[13px] font-semibold text-text">{currentLabel}</p>
      )}
    </div>
  )
}
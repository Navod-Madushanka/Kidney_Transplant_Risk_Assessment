// src/components/ui/ToggleSwitch.jsx
import { useId } from "react"

/**
 * An iOS-style switch — a pill track with a sliding circular knob, rather
 * than a checkbox. Built on a real button with role="switch" so assistive
 * tech announces it correctly (checkbox semantics would be wrong here: a
 * switch fires its effect immediately, a checkbox implies "submit later").
 *
 * Usage:
 *   <ToggleSwitch
 *     label="Previous transplant"
 *     checked={sensitization.previous_transplant}
 *     onChange={(checked) => setSensitization({ previous_transplant: checked })}
 *     helperText="+2.0 sensitization points"
 *   />
 */
export default function ToggleSwitch({
  label,
  checked = false,
  onChange,
  disabled = false,
  helperText,
  className = "",
  id,
}) {
  const generatedId = useId()
  const switchId = id ?? generatedId

  return (
    <div className={["flex items-center justify-between gap-4 py-1", className].join(" ")}>
      <div className="min-w-0">
        {label && (
          <label htmlFor={switchId} className="text-[15px] font-medium text-text block truncate">
            {label}
          </label>
        )}
        {helperText && (
          <p className="text-[13px] text-text-muted mt-0.5">{helperText}</p>
        )}
      </div>

      <button
        id={switchId}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange?.(!checked)}
        className={[
          "relative shrink-0 h-[31px] w-[51px] rounded-full transition-colors duration-200",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
          "disabled:opacity-40 disabled:cursor-not-allowed",
          checked ? "bg-clear" : "bg-border",
        ].join(" ")}
      >
        <span
          aria-hidden="true"
          className={[
            "absolute top-[2px] left-[2px] h-[27px] w-[27px] rounded-full bg-white shadow-card",
            "transition-transform duration-200 ease-out",
            checked ? "translate-x-[20px]" : "translate-x-0",
          ].join(" ")}
        />
      </button>
    </div>
  )
}
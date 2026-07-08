// src/components/ui/InputField.jsx
import { useId } from "react"

/**
 * Usage:
 *   <InputField label="NIC number" required value={nic} onChange={...} />
 *   <InputField label="Date of birth" type="date" error="Enter a valid date" />
 *   <InputField label="MFI cutoff" helperText="Default is 2000" />
 */
export default function InputField({
  label,
  error,
  helperText,
  required = false,
  className = "",
  id,
  ...props
}) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const describedBy = error
    ? `${inputId}-error`
    : helperText
    ? `${inputId}-helper`
    : undefined

  return (
    <div className={["flex flex-col gap-1.5", className].join(" ")}>
      {label && (
        <label htmlFor={inputId} className="text-[13px] font-semibold text-text">
          {label}
          {required && (
            <span className="text-high-risk ml-0.5" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}
      <input
        id={inputId}
        required={required}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={[
          "h-11 rounded-md border px-3.5 text-[15px] text-text bg-surface",
          "placeholder:text-text-muted",
          "transition-colors duration-150",
          "focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent",
          "disabled:bg-bg disabled:text-text-muted disabled:cursor-not-allowed",
          error
            ? "border-high-risk focus:ring-high-risk/20 focus:border-high-risk"
            : "border-border",
        ].join(" ")}
        {...props}
      />
      {error ? (
        <p id={`${inputId}-error`} className="text-[13px] text-high-risk font-medium">
          {error}
        </p>
      ) : helperText ? (
        <p id={`${inputId}-helper`} className="text-[13px] text-text-muted">
          {helperText}
        </p>
      ) : null}
    </div>
  )
}
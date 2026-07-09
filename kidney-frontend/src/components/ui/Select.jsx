// src/components/ui/Select.jsx
import { useId } from "react"

/**
 * Wraps a native <select>, deliberately — on iOS and Android this renders the
 * OS's own picker wheel/sheet, which is exactly the "native app" feel we want
 * and is more reliable on touch devices than a custom-built dropdown.
 *
 * Usage:
 *   <Select
 *     label="Blood group"
 *     value={bloodType}
 *     onChange={(e) => setBloodType(e.target.value)}
 *     options={[
 *       { value: "O", label: "O" },
 *       { value: "A", label: "A" },
 *       { value: "B", label: "B" },
 *       { value: "AB", label: "AB" },
 *     ]}
 *     placeholder="Select blood group"
 *   />
 */
export default function Select({
  label,
  error,
  helperText,
  required = false,
  options = [],
  placeholder,
  className = "",
  id,
  ...props
}) {
  const generatedId = useId()
  const selectId = id ?? generatedId
  const describedBy = error
    ? `${selectId}-error`
    : helperText
    ? `${selectId}-helper`
    : undefined

  return (
    <div className={["flex flex-col gap-1.5", className].join(" ")}>
      {label && (
        <label htmlFor={selectId} className="text-[13px] font-semibold text-text">
          {label}
          {required && (
            <span className="text-high-risk ml-0.5" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}
      <div className="relative">
        <select
          id={selectId}
          required={required}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          defaultValue={props.value === undefined ? "" : undefined}
          className={[
            "h-11 w-full appearance-none rounded-md border px-3.5 pr-9 text-[15px] text-text bg-surface",
            "transition-colors duration-150",
            "focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent",
            "disabled:bg-bg disabled:text-text-muted disabled:cursor-not-allowed",
            error
              ? "border-high-risk focus:ring-high-risk/20 focus:border-high-risk"
              : "border-border",
          ].join(" ")}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <svg
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted"
          viewBox="0 0 20 20"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M5 7.5L10 12.5L15 7.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      {error ? (
        <p id={`${selectId}-error`} className="text-[13px] text-high-risk font-medium">
          {error}
        </p>
      ) : helperText ? (
        <p id={`${selectId}-helper`} className="text-[13px] text-text-muted">
          {helperText}
        </p>
      ) : null}
    </div>
  )
}
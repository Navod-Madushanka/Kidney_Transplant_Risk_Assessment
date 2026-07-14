// src/components/ui/SegmentedControl.jsx

/**
 * An iOS-style segmented control — a single track with a sliding highlight,
 * for a small, static, always-visible set of mutually exclusive options.
 * Use this instead of Select when: the option count is small (2–5), the
 * options never change at runtime, and the person benefits from seeing every
 * choice at once rather than opening a picker (e.g. blood type). For longer
 * or dynamic option sets (e.g. HLA locus), keep using Select.
 *
 * Usage:
 *   <SegmentedControl
 *     label="Blood group"
 *     options={BLOOD_TYPE_OPTIONS}
 *     value={form.bloodType}
 *     onChange={(value) => updateField("bloodType")(value)}
 *     error={errors.bloodType}
 *     required
 *   />
 */
export default function SegmentedControl({
  label,
  options = [],
  value,
  onChange,
  required = false,
  error,
  helperText,
  disabled = false,
  className = "",
}) {
  const activeIndex = Math.max(
    0,
    options.findIndex((opt) => opt.value === value)
  )
  const hasSelection = options.some((opt) => opt.value === value)

  return (
    <div className={["flex flex-col gap-1.5", className].join(" ")}>
      {label && (
        <span className="text-[13px] font-semibold text-text">
          {label}
          {required && (
            <span className="text-high-risk ml-0.5" aria-hidden="true">
              *
            </span>
          )}
        </span>
      )}

      <div
        role="radiogroup"
        aria-label={label}
        aria-invalid={!!error}
        className={[
          "relative grid h-11 rounded-md border p-[3px] bg-bg",
          error ? "border-high-risk" : "border-border",
          disabled ? "opacity-50 pointer-events-none" : "",
        ].join(" ")}
        style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      >
        {/* Sliding highlight — one element, positioned under the active segment */}
        {hasSelection && (
          <span
            aria-hidden="true"
            className="absolute inset-y-[3px] rounded-[5px] bg-surface shadow-card transition-transform duration-200 ease-out"
            style={{
              width: `calc(${100 / options.length}% - 3px)`,
              transform: `translateX(calc(${activeIndex * 100}% + ${activeIndex * 3}px))`,
            }}
          />
        )}

        {options.map((option) => {
          const isActive = option.value === value
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={isActive}
              disabled={disabled}
              onClick={() => onChange?.(option.value)}
              className={[
                "relative z-10 rounded-[5px] text-[14px] font-semibold transition-colors duration-150",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                isActive ? "text-text" : "text-text-muted",
              ].join(" ")}
            >
              {option.label}
            </button>
          )
        })}
      </div>

      {error ? (
        <p className="text-[13px] text-high-risk font-medium">{error}</p>
      ) : helperText ? (
        <p className="text-[13px] text-text-muted">{helperText}</p>
      ) : null}
    </div>
  )
}
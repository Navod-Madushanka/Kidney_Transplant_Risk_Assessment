// src/components/ui/Button.jsx

const VARIANT_STYLES = {
  primary:
    "bg-accent text-white hover:bg-accent-hover active:bg-accent-hover disabled:bg-border disabled:text-text-muted",
  secondary:
    "bg-surface text-text border border-border hover:bg-bg active:bg-bg disabled:text-text-muted disabled:bg-bg",
  ghost:
    "bg-transparent text-accent hover:bg-accent-subtle active:bg-accent-subtle disabled:text-text-muted",
  destructive:
    "bg-high-risk text-white hover:brightness-90 active:brightness-90 disabled:bg-border disabled:text-text-muted",
}

const SIZE_STYLES = {
  sm: "h-9 px-3 text-[13px] gap-1.5",
  md: "h-11 px-4 text-[15px] gap-2",
  lg: "h-[52px] px-6 text-[17px] gap-2",
}

/**
 * Primary button component. Every interactive surface in the app should route
 * through this rather than a raw <button>, so focus, disabled, and loading
 * states stay consistent everywhere (this matters a lot for a clinical tool
 * used under time pressure).
 *
 * Usage:
 *   <Button onClick={runCheck}>Run compatibility check</Button>
 *   <Button variant="destructive" onClick={haltReport}>Halt report</Button>
 *   <Button variant="secondary" size="sm">Cancel</Button>
 *   <Button loading>Saving…</Button>
 */
export default function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  icon: Icon,
  className = "",
  type = "button",
  ...props
}) {
  const isDisabled = disabled || loading

  return (
    <button
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={[
        "inline-flex items-center justify-center rounded-md font-semibold whitespace-nowrap",
        "transition-colors duration-150 select-none",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        "disabled:cursor-not-allowed",
        VARIANT_STYLES[variant],
        SIZE_STYLES[size],
        className,
      ].join(" ")}
      {...props}
    >
      {loading ? (
        <span
          className="h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin"
          aria-hidden="true"
        />
      ) : Icon ? (
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      ) : null}
      {children}
    </button>
  )
}
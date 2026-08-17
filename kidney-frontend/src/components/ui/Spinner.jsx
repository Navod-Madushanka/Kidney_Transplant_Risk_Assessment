// src/components/ui/Spinner.jsx

const SIZE_STYLES = {
  sm: "h-4 w-4 border-2",
  md: "h-8 w-8 border-2",
  lg: "h-10 w-10 border-[3px]",
}

/**
 * Usage:
 *   <Spinner />
 *   <Spinner size="sm" />
 *   <div className="flex justify-center py-16"><Spinner /></div>
 *
 * The one loading indicator every page should use -- extracted from three
 * near-identical hand-rolled copies (ExchangePoolPage, Button's `loading`
 * prop, ExchangeCycleGraph) into a single component.
 */
export default function Spinner({ size = "md", className = "" }) {
  return (
    <div
      className={[
        "rounded-full border-border border-t-accent animate-spin",
        SIZE_STYLES[size],
        className,
      ].join(" ")}
      role="status"
      aria-label="Loading"
    />
  )
}

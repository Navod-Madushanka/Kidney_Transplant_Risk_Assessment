// src/components/ui/Badge.jsx

// Every clinical status in the app should map to one of these keys, never a
// one-off color. Keeping this map as the single source of truth means "red"
// always means the same clinical thing everywhere in the product.
const STATUS_STYLES = {
  pass: "bg-clear-subtle text-clear",
  clear: "bg-clear-subtle text-clear",
  fail: "bg-high-risk-subtle text-high-risk",
  halt: "bg-high-risk-subtle text-high-risk",
  low: "bg-clear-subtle text-clear",
  moderate: "bg-moderate-subtle text-moderate",
  "high-moderate": "bg-high-moderate-subtle text-high-moderate",
  "high-risk": "bg-high-risk-subtle text-high-risk",
  pending: "bg-accent-subtle text-accent",
  neutral: "bg-bg text-text-muted border border-border",
}

const STATUS_LABELS = {
  pass: "Pass",
  clear: "Clear",
  fail: "Fail",
  halt: "Halted",
  low: "Low Risk",
  moderate: "Moderate Risk",
  "high-moderate": "High-Moderate Risk",
  "high-risk": "High Genetic Risk",
  pending: "Needs Review",
  neutral: "—",
}

/**
 * Usage:
 *   <Badge status="pass" />                  -> green "Pass" pill
 *   <Badge status="high-moderate" />         -> orange "High-Moderate Risk" pill
 *   <Badge status="pending">3 rows flagged</Badge>  -> custom label, same color
 */
export default function Badge({ status = "neutral", children, className = "" }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.neutral
  const label = children ?? STATUS_LABELS[status] ?? status

  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[13px] font-semibold leading-none",
        style,
        className,
      ].join(" ")}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {label}
    </span>
  )
}
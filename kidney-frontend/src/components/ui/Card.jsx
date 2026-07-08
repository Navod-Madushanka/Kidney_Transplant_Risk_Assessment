// src/components/ui/Card.jsx

/**
 * The base surface for almost everything in the app — status cards, forms,
 * table containers, report sections. Keeps the same border/shadow/radius
 * everywhere so the UI reads as one coherent system rather than assembled
 * pieces.
 *
 * Usage:
 *   <Card>
 *     <Card.Header title="ABO Compatibility" subtitle="Recipient vs donor blood type" />
 *     ...content...
 *   </Card>
 *
 *   <Card padded={false}>  // e.g. wrapping a Table that manages its own padding
 */
export default function Card({
  children,
  className = "",
  padded = true,
  as: Component = "div",
  ...props
}) {
  return (
    <Component
      className={[
        "bg-surface border border-border rounded-lg shadow-card",
        padded ? "p-5 sm:p-6" : "",
        className,
      ].join(" ")}
      {...props}
    >
      {children}
    </Component>
  )
}

Card.Header = function CardHeader({ title, subtitle, action, className = "" }) {
  return (
    <div className={["flex items-start justify-between gap-4 mb-4", className].join(" ")}>
      <div>
        <h3 className="text-[17px] font-semibold text-text leading-tight">{title}</h3>
        {subtitle && (
          <p className="text-[13px] text-text-muted mt-0.5">{subtitle}</p>
        )}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
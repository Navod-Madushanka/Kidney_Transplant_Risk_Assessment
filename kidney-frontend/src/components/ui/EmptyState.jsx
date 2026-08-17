// src/components/ui/EmptyState.jsx

/**
 * Usage:
 *   <EmptyState message="No incompatible pairs in the exchange pool right now." />
 *   <EmptyState message="Couldn't load the exchange pool. Please try refreshing." />
 *
 * The one hand-rolled "bordered box with muted centered text" every page
 * used to build for itself (empty pools, load errors, no results).
 */
export default function EmptyState({ message, className = "" }) {
  return (
    <div
      className={[
        "border border-border rounded-lg p-8 text-center bg-surface",
        className,
      ].join(" ")}
    >
      <p className="text-[15px] text-text-muted">{message}</p>
    </div>
  )
}

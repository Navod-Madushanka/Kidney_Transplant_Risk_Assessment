// src/context/ReviewedReportsProvider.jsx
import { useCallback, useMemo, useState } from "react"
import { ReviewedReportsContext } from "./ReviewedReportsContext"

/**
 * Tracks which halted match reports (ABO fail / DSA trigger) the doctor has
 * already opened, so the dashboard's alert banner can stop nagging about
 * ones they've seen. Deliberately in-memory only — a plain useState Set,
 * not localStorage/sessionStorage — so it resets on every reload. That's
 * intentional: this is a "don't miss something in this session" aid, not a
 * persistent audit trail (the real audit trail is server-side audit_logs).
 *
 * Wrap the app (or just the dashboard route) with <ReviewedReportsProvider>,
 * then read/write via the useReviewedReports() hook.
 */
export function ReviewedReportsProvider({ children }) {
  const [reviewedIds, setReviewedIds] = useState(() => new Set())

  const markReviewed = useCallback((reportId) => {
    setReviewedIds((prev) => {
      if (prev.has(reportId)) return prev
      const next = new Set(prev)
      next.add(reportId)
      return next
    })
  }, [])

  const isReviewed = useCallback(
    (reportId) => reviewedIds.has(reportId),
    [reviewedIds]
  )

  const value = useMemo(
    () => ({ isReviewed, markReviewed }),
    [isReviewed, markReviewed]
  )

  return (
    <ReviewedReportsContext.Provider value={value}>
      {children}
    </ReviewedReportsContext.Provider>
  )
}
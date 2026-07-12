// src/hooks/useReviewedReports.js
import { useContext } from "react"
import { ReviewedReportsContext } from "../context/ReviewedReportsContext"

export function useReviewedReports() {
  const context = useContext(ReviewedReportsContext)
  if (!context) {
    throw new Error(
      "useReviewedReports must be used within a ReviewedReportsProvider"
    )
  }
  return context
}
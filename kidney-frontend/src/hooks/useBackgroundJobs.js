// src/hooks/useBackgroundJobs.js
import { useContext } from "react"
import { BackgroundJobsContext } from "../context/BackgroundJobsContext"

export function useBackgroundJobs() {
  const context = useContext(BackgroundJobsContext)
  if (!context) {
    throw new Error("useBackgroundJobs must be used within a BackgroundJobsProvider")
  }
  return context
}

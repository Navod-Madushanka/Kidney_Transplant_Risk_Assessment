// src/hooks/usePendingExchangeProposalsCount.js
import { useEffect, useState } from "react"
import { listExchangeProposals } from "../api/exchangeProposals"

// Part K, K6: "there is no notification infrastructure in this codebase" --
// the pending-decisions badge on the Exchange nav item (Sidebar/TabBar) is
// fed by polling GET /exchange/proposals?mine=true, the same shape
// BackgroundJobsProvider already uses for out-of-band state. 30s is a
// coordinator-facing background count, not a live job progress bar (see
// useExtractionJobPolling's 2.5s), so a slower cadence is enough.
const POLL_INTERVAL_MS = 30000

export function usePendingExchangeProposalsCount() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timeoutId

    async function poll() {
      try {
        const proposals = await listExchangeProposals(true)
        if (!cancelled) setCount(proposals.length)
      } catch {
        // Transient failure -- keep the last known count and try again on
        // the next tick rather than flashing the badge to zero.
      }
      if (!cancelled) timeoutId = setTimeout(poll, POLL_INTERVAL_MS)
    }

    poll()
    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [])

  return count
}

// src/pages/ReportsListPage.jsx
import { useEffect, useState } from "react"
import { getDashboardRecentReports } from "../api/dashboard"
import Card from "../components/ui/Card"
import RecentReportRow from "../components/domain/dashboard/RecentReportRow"

// No dedicated "list all reports" endpoint exists yet — this reuses the
// dashboard's recent-reports endpoint with a high limit instead of adding
// a new backend route just for this page. Revisit with real pagination
// (see the roadmap's Phase 5) once report volume makes that necessary.
const REPORTS_PAGE_LIMIT = 200

export default function ReportsListPage() {
  const [state, setState] = useState({ status: "loading", reports: [] })

  useEffect(() => {
    let cancelled = false
    getDashboardRecentReports(REPORTS_PAGE_LIMIT)
      .then((reports) => !cancelled && setState({ status: "loaded", reports }))
      .catch(() => !cancelled && setState({ status: "error", reports: [] }))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-[22px] font-bold text-text">Reports</h1>
      </div>

      {state.status === "loading" && (
        <div className="flex justify-center py-16">
          <div
            className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin"
            role="status"
            aria-label="Loading"
          />
        </div>
      )}

      {state.status === "error" && (
        <div className="border border-border rounded-lg p-8 text-center bg-surface">
          <p className="text-[15px] text-text-muted">Couldn't load reports. Please try refreshing.</p>
        </div>
      )}

      {state.status === "loaded" && state.reports.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center bg-surface">
          <p className="text-[15px] text-text-muted">No compatibility checks run yet.</p>
        </div>
      )}

      {state.status === "loaded" && state.reports.length > 0 && (
        <Card padded={false}>
          <div className="divide-y divide-border">
            {state.reports.map((report) => (
              <RecentReportRow key={report.id} report={report} />
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

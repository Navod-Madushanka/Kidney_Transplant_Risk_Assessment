// src/components/domain/dashboard/RecentReportRow.jsx
import { Link } from "react-router-dom"
import Badge from "../../ui/Badge"
import { reportBadgeProps } from "../../../constants/reportStatus"

/**
 * One row in the dashboard's "Recent reports" list — patient → donor, date,
 * and a status/tier badge. Mirrors PatientRow/DonorRow's layout so the three
 * list styles in the app read as one system.
 *
 * Usage:
 *   <RecentReportRow report={report} />
 */
export default function RecentReportRow({ report }) {
  const { status, label } = reportBadgeProps(report)

  return (
    <Link
      to={`/reports/${report.id}`}
      className="flex items-center justify-between gap-3 px-4 py-3.5 active:bg-bg transition-colors"
    >
      <div className="min-w-0">
        <p className="text-[15px] font-semibold text-text truncate">
          {report.patient_full_name} <span className="text-text-muted font-normal">→</span> {report.donor_full_name}
        </p>
        <p className="text-[13px] text-text-muted">
          {new Date(report.created_at).toLocaleDateString()}
        </p>
      </div>
      <Badge status={status}>{label}</Badge>
    </Link>
  )
}
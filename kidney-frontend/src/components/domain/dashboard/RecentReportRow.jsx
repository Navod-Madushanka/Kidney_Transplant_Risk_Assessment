// src/components/domain/dashboard/RecentReportRow.jsx
import { Link } from "react-router-dom"
import Badge from "../../ui/Badge"

const RISK_TIER_TO_BADGE_STATUS = {
  "Low Risk": "low",
  "Moderate Risk": "moderate",
  "High-Moderate Risk": "high-moderate",
  "High Genetic Risk": "high-risk",
}

function badgeProps(report) {
  if (report.overall_status === "halted_abo_fail") {
    return { status: "fail", label: "ABO Fail" }
  }
  if (report.overall_status === "halted_dsa_trigger") {
    return { status: "halt", label: "DSA Halt" }
  }
  if (report.risk_tier) {
    return { status: RISK_TIER_TO_BADGE_STATUS[report.risk_tier] ?? "neutral", label: report.risk_tier }
  }
  return { status: "neutral", label: "—" }
}

/**
 * One row in the dashboard's "Recent reports" list — patient → donor, date,
 * and a status/tier badge. Mirrors PatientRow/DonorRow's layout so the three
 * list styles in the app read as one system.
 *
 * Usage:
 *   <RecentReportRow report={report} />
 */
export default function RecentReportRow({ report }) {
  const { status, label } = badgeProps(report)

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
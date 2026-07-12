// src/components/domain/dashboard/HaltedReportBanner.jsx
import { Link } from "react-router-dom"
import { useReviewedReports } from "../../../hooks/useReviewedReports"

const HALTED_STATUSES = new Set(["halted_abo_fail", "halted_dsa_trigger"])

const HALTED_LABELS = {
  halted_abo_fail: "ABO incompatible",
  halted_dsa_trigger: "Donor-specific antibody detected",
}

/**
 * Slim, unmissable alert banner for halted reports (ABO fail / DSA trigger)
 * the doctor hasn't opened yet this session. Sits above everything else on
 * the dashboard — the one thing that shouldn't require scrolling to notice.
 * Renders nothing once there's nothing unreviewed, so it never adds empty
 * whitespace to the top of the screen.
 *
 * Usage:
 *   <HaltedReportBanner reports={recentReports} />
 *
 * `reports` is the same RecentReportSummary[] shape used by RecentReportRow;
 * this component filters down to halted + unreviewed itself.
 */
export default function HaltedReportBanner({ reports = [] }) {
  const { isReviewed } = useReviewedReports()

  const unreviewedHalted = reports.filter(
    (report) => HALTED_STATUSES.has(report.overall_status) && !isReviewed(report.id)
  )

  if (unreviewedHalted.length === 0) return null

  return (
    <div className="rounded-lg border border-high-risk/30 bg-high-risk-subtle p-4 flex flex-col gap-2">
      <p className="text-[14px] font-semibold text-high-risk">
        {unreviewedHalted.length === 1
          ? "1 halted report needs review"
          : `${unreviewedHalted.length} halted reports need review`}
      </p>

      <ul className="flex flex-col gap-1.5">
        {unreviewedHalted.map((report) => (
          <li key={report.id}>
            <Link
              to={`/reports/${report.id}`}
              className="flex items-center justify-between gap-3 text-[14px] active:opacity-70"
            >
              <span className="text-text font-medium truncate">
                {report.patient_full_name} → {report.donor_full_name}
              </span>
              <span className="text-high-risk shrink-0">
                {HALTED_LABELS[report.overall_status] ?? report.overall_status}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
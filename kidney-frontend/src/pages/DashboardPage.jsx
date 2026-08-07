// src/pages/DashboardPage.jsx
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"
import { getDashboardPatients, getDashboardRecentReports } from "../api/dashboard"
import Card from "../components/ui/Card"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import HaltedReportBanner from "../components/domain/dashboard/HaltedReportBanner"
import RecentReportRow from "../components/domain/dashboard/RecentReportRow"
import { reportBadgeProps } from "../constants/reportStatus"

const PATIENT_LIST_CAP = 5
const RECENT_REPORTS_CAP = 5

function DashboardPatientRow({ patient }) {
  const { status, label } = reportBadgeProps(patient.latest_report)

  return (
    <Link
      to={`/patients/${patient.id}`}
      className="flex items-center justify-between gap-3 px-4 py-3.5 active:bg-bg transition-colors"
    >
      <div className="min-w-0">
        <p className="text-[15px] font-semibold text-text truncate">{patient.full_name}</p>
        <p className="text-[13px] text-text-muted">
          {patient.nic_number || "No NIC on file"}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Badge status="neutral">{patient.blood_type}</Badge>
        <Badge status={status}>{label}</Badge>
      </div>
    </Link>
  )
}

function SectionHeader({ title, viewAllTo }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h2 className="text-[17px] font-semibold text-text">{title}</h2>
      <Link to={viewAllTo} className="text-[13px] font-semibold text-accent active:text-accent-hover">
        View all
      </Link>
    </div>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()

  const [patientsState, setPatientsState] = useState({ status: "loading", patients: [] })
  const [reportsState, setReportsState] = useState({ status: "loading", reports: [] })

  useEffect(() => {
    let cancelled = false

    getDashboardPatients()
      .then((patients) => !cancelled && setPatientsState({ status: "loaded", patients }))
      .catch(() => !cancelled && setPatientsState({ status: "error", patients: [] }))

    getDashboardRecentReports(RECENT_REPORTS_CAP)
      .then((reports) => !cancelled && setReportsState({ status: "loaded", reports }))
      .catch(() => !cancelled && setReportsState({ status: "error", reports: [] }))

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-[20px] font-bold text-text leading-tight">
          {user?.full_name ? `Hi, ${user.full_name}` : "Hi"}
        </p>
        <p className="text-[14px] text-text-muted">{user?.hospital_name ?? "Kidney Transplant Compatibility System"}</p>
      </div>

      <Link to="/checks/new">
        <Button size="lg" className="w-full">
          New compatibility check
        </Button>
      </Link>
      <Link
        to="/checks/start-from-records"
        className="text-[13px] font-semibold text-accent text-center -mt-3"
      >
        Start from an existing patient &amp; donor's records instead
      </Link>

      {reportsState.status === "loaded" && <HaltedReportBanner reports={reportsState.reports} />}

      <div>
        <SectionHeader title="Patients" viewAllTo="/patients" />

        <Card padded={false}>
          {patientsState.status === "loading" && (
            <div className="flex justify-center py-8">
              <div
                className="h-6 w-6 rounded-full border-2 border-border border-t-accent animate-spin"
                role="status"
                aria-label="Loading"
              />
            </div>
          )}

          {patientsState.status === "error" && (
            <p className="text-[14px] text-text-muted p-4">Couldn't load patients.</p>
          )}

          {patientsState.status === "loaded" && patientsState.patients.length === 0 && (
            <p className="text-[14px] text-text-muted p-4">No patients yet.</p>
          )}

          {patientsState.status === "loaded" && patientsState.patients.length > 0 && (
            <div className="divide-y divide-border">
              {patientsState.patients.slice(0, PATIENT_LIST_CAP).map((patient) => (
                <DashboardPatientRow key={patient.id} patient={patient} />
              ))}
            </div>
          )}
        </Card>
      </div>

      <div>
        <SectionHeader title="Recent reports" viewAllTo="/reports" />

        <Card padded={false}>
          {reportsState.status === "loading" && (
            <div className="flex justify-center py-8">
              <div
                className="h-6 w-6 rounded-full border-2 border-border border-t-accent animate-spin"
                role="status"
                aria-label="Loading"
              />
            </div>
          )}

          {reportsState.status === "error" && (
            <p className="text-[14px] text-text-muted p-4">Couldn't load recent reports.</p>
          )}

          {reportsState.status === "loaded" && reportsState.reports.length === 0 && (
            <p className="text-[14px] text-text-muted p-4">No compatibility checks run yet.</p>
          )}

          {reportsState.status === "loaded" && reportsState.reports.length > 0 && (
            <div className="divide-y divide-border">
              {reportsState.reports.map((report) => (
                <RecentReportRow key={report.id} report={report} />
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
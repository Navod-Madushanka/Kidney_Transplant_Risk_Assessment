// src/pages/PatientDetailPage.jsx
import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import {
  getPatient,
  getPatientHlaTypings,
  getPatientAntibodyProfiles,
  listPatientSensitizationEvents,
  replacePatientHlaTypings,
  replacePatientAntibodyProfiles,
  createSensitizationEvents,
  getPatientReports,
} from "../api/patients"
import { ApiError } from "../api/client"
import Card from "../components/ui/Card"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import HlaTypingEditor from "../components/domain/hla/HlaTypingEditor"
import AntibodyProfileEditor from "../components/domain/antibody/AntibodyProfileEditor"
import SensitizationEventEditor from "../components/domain/sensitization/SensitizationEventEditor"

// Calls a not-yet-guaranteed GET endpoint. Treats 404 as "not built yet"
// (shows the locked editor state) rather than a hard page error.
async function loadOptional(fetchFn) {
  try {
    const data = await fetchFn()
    return { state: "loaded", data }
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return { state: "not_available", data: [] }
    return { state: "error", data: [] }
  }
}

export default function PatientDetailPage() {
  const { patientId } = useParams()
  const [patient, setPatient] = useState(null)
  const [patientLoadState, setPatientLoadState] = useState("loading")

  const [hlaState, setHlaState] = useState({ state: "loading", data: [] })
  const [antibodyState, setAntibodyState] = useState({ state: "loading", data: [] })
  const [sensitizationState, setSensitizationState] = useState({ state: "loading", data: [] })
  const [reports, setReports] = useState([])

  useEffect(() => {
    let cancelled = false

    getPatient(patientId)
      .then((data) => !cancelled && (setPatient(data), setPatientLoadState("loaded")))
      .catch(() => !cancelled && setPatientLoadState("error"))

    loadOptional(() => getPatientHlaTypings(patientId)).then((r) => !cancelled && setHlaState(r))
    loadOptional(() => getPatientAntibodyProfiles(patientId)).then((r) => !cancelled && setAntibodyState(r))
    loadOptional(() => listPatientSensitizationEvents(patientId)).then((r) => !cancelled && setSensitizationState(r))
    getPatientReports(patientId).then((r) => !cancelled && setReports(r)).catch(() => {})

    return () => {
      cancelled = true
    }
  }, [patientId])

  if (patientLoadState === "loading") {
    return (
      <div className="flex justify-center py-16">
        <div className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin" role="status" aria-label="Loading" />
      </div>
    )
  }

  if (patientLoadState === "error" || !patient) {
    return <p className="text-[15px] text-text-muted">Couldn't load this patient.</p>
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-[22px] font-bold text-text">{patient.full_name}</h1>
          <Badge status="neutral">{patient.blood_type}</Badge>
        </div>
        <p className="text-[14px] text-text-muted">
          {patient.nic_number || "No NIC on file"} · DOB {patient.date_of_birth}
        </p>
      </div>

      <Card>
        <Card.Header
          title="Recent reports"
          action={
            <Link to={`/checks/new?patientId=${patient.id}`}>
              <Button size="sm">New compatibility check</Button>
            </Link>
          }
        />
        {reports.length === 0 ? (
          <p className="text-[14px] text-text-muted">No compatibility checks run yet.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {reports.map((report) => (
              <li key={report.id}>
                <Link
                  to={`/reports/${report.id}`}
                  className="flex items-center justify-between py-2.5 hover:bg-bg -mx-1 px-1 rounded transition-colors"
                >
                  <span className="text-[14px] text-text-muted">
                    {new Date(report.created_at).toLocaleDateString()}
                  </span>
                  <Badge status={report.overall_status?.toLowerCase().replace(/_/g, "-")}>
                    {report.overall_status}
                  </Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <HlaTypingEditor
        loadState={hlaState.state}
        initialEntries={hlaState.data}
        onSave={(entries) => replacePatientHlaTypings(patient.id, entries)}
      />

      <AntibodyProfileEditor
        loadState={antibodyState.state}
        initialEntries={antibodyState.data}
        onSave={(entries) => replacePatientAntibodyProfiles(patient.id, entries)}
      />

      <SensitizationEventEditor
        loadState={sensitizationState.state}
        existingEvents={sensitizationState.data}
        onAdd={(entries) => createSensitizationEvents(patient.id, entries)}
      />
    </div>
  )
}
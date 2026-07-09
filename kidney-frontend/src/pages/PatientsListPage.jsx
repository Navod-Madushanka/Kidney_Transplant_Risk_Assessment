// src/pages/PatientsListPage.jsx
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { listPatients } from "../api/patients"
import Button from "../components/ui/Button"
import Badge from "../components/ui/Badge"

function PatientRow({ patient }) {
  return (
    <Link
      to={`/patients/${patient.id}`}
      className="flex items-center justify-between gap-3 px-4 py-3.5 hover:bg-bg transition-colors"
    >
      <div className="min-w-0">
        <p className="text-[15px] font-semibold text-text truncate">{patient.full_name}</p>
        <p className="text-[13px] text-text-muted">
          {patient.nic_number || "No NIC on file"} · DOB {patient.date_of_birth}
        </p>
      </div>
      <Badge status="neutral">{patient.blood_type}</Badge>
    </Link>
  )
}

export default function PatientsListPage() {
  const [state, setState] = useState({ status: "loading", patients: [] })

  useEffect(() => {
    let cancelled = false
    listPatients()
      .then((patients) => !cancelled && setState({ status: "loaded", patients }))
      .catch(() => !cancelled && setState({ status: "error", patients: [] }))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-[22px] font-bold text-text">Patients</h1>
        <Link to="/patients/new">
          <Button>Add patient</Button>
        </Link>
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
          <p className="text-[15px] text-text-muted">Couldn't load patients. Please try refreshing.</p>
        </div>
      )}

      {state.status === "loaded" && state.patients.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center bg-surface">
          <p className="text-[15px] text-text-muted">No patients yet.</p>
        </div>
      )}

      {state.status === "loaded" && state.patients.length > 0 && (
        <div className="bg-surface border border-border rounded-lg divide-y divide-border overflow-hidden">
          {state.patients.map((patient) => (
            <PatientRow key={patient.id} patient={patient} />
          ))}
        </div>
      )}
    </div>
  )
}
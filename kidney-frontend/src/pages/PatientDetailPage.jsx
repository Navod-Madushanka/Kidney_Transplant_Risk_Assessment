// src/pages/PatientDetailPage.jsx
import { useEffect, useState } from "react"
import { useNavigate, useParams, Link } from "react-router-dom"
import {
  getPatient,
  updatePatient,
  deletePatient,
  getPatientHlaTypings,
  getPatientAntibodyProfiles,
  listPatientSensitizationEvents,
  replacePatientHlaTypings,
  replacePatientAntibodyProfiles,
  createSensitizationEvents,
  getPatientReports,
} from "../api/patients"
import {
  listPatientReportFiles,
  uploadPatientReportFile,
  deletePatientReportFile,
  downloadPatientReportFile,
} from "../api/reportFiles"
import Card from "../components/ui/Card"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import Modal from "../components/ui/Modal"
import PatientForm from "../components/domain/patient/PatientForm"
import HlaTypingEditor from "../components/domain/hla/HlaTypingEditor"
import AntibodyProfileEditor from "../components/domain/antibody/AntibodyProfileEditor"
import SensitizationEventEditor from "../components/domain/sensitization/SensitizationEventEditor"
import ReportFilesCard from "../components/domain/reportFiles/ReportFilesCard"
import PairDocumentsCard from "../components/domain/reportFiles/PairDocumentsCard"
import { enumToForm } from "../utils/formValue"
import { reportBadgeProps } from "../constants/reportStatus"
import { PATIENT_REPORT_CATEGORY_OPTIONS } from "../constants/reportFileCategory"

async function loadEditorData(fetchFn) {
  try {
    const data = await fetchFn()
    return { state: "loaded", data }
  } catch {
    return { state: "error", data: [] }
  }
}

export default function PatientDetailPage() {
  const { patientId } = useParams()
  const navigate = useNavigate()
  const [patient, setPatient] = useState(null)
  const [patientLoadState, setPatientLoadState] = useState("loading")

  const [hlaState, setHlaState] = useState({ state: "loading", data: [] })
  const [antibodyState, setAntibodyState] = useState({ state: "loading", data: [] })
  const [sensitizationState, setSensitizationState] = useState({ state: "loading", data: [] })
  const [reportFilesState, setReportFilesState] = useState({ state: "loading", data: [] })
  const [reports, setReports] = useState([])

  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isSavingEdit, setIsSavingEdit] = useState(false)

  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState("")

  useEffect(() => {
    let cancelled = false

    getPatient(patientId)
      .then((data) => !cancelled && (setPatient(data), setPatientLoadState("loaded")))
      .catch(() => !cancelled && setPatientLoadState("error"))

    loadEditorData(() => getPatientHlaTypings(patientId)).then((r) => !cancelled && setHlaState(r))
    loadEditorData(() => getPatientAntibodyProfiles(patientId)).then((r) => !cancelled && setAntibodyState(r))
    loadEditorData(() => listPatientSensitizationEvents(patientId)).then((r) => !cancelled && setSensitizationState(r))
    loadEditorData(() => listPatientReportFiles(patientId)).then((r) => !cancelled && setReportFilesState(r))
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

  async function handleEditSubmit(payload) {
    setIsSavingEdit(true)
    try {
      const updated = await updatePatient(patient.id, payload)
      setPatient(updated)
      setIsEditOpen(false)
    } finally {
      setIsSavingEdit(false)
    }
  }

  async function handleDeleteConfirm() {
    setDeleteError("")
    setIsDeleting(true)
    try {
      await deletePatient(patient.id)
      navigate("/patients")
    } catch (err) {
      setDeleteError(err.message || "Couldn't delete this patient. Please try again.")
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-[22px] font-bold text-text">{patient.full_name}</h1>
            <Badge status="neutral">{patient.blood_type}</Badge>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setIsEditOpen(true)}>
              Edit details
            </Button>
            <Button variant="destructive" size="sm" onClick={() => setIsDeleteOpen(true)}>
              Delete patient
            </Button>
          </div>
        </div>
        <p className="text-[14px] text-text-muted">
          {patient.nic_number || "No NIC on file"} · DOB {patient.date_of_birth}
        </p>
      </div>

      <Modal open={isEditOpen} onClose={() => setIsEditOpen(false)} title="Edit patient details">
        <PatientForm
          mode="edit"
          submitLabel="Save changes"
          isSubmitting={isSavingEdit}
          initialValues={{
            fullName: patient.full_name,
            dateOfBirth: patient.date_of_birth,
            bloodType: patient.blood_type,
            rhFactor: patient.rh_factor,
            nicNumber: patient.nic_number || "",
            sex: enumToForm(patient.sex),
            weightKg: patient.weight_kg ?? "",
          }}
          onSubmit={handleEditSubmit}
        />
      </Modal>

      <Modal
        open={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        title={`Delete ${patient.full_name}?`}
      >
        <p className="text-[15px] text-text-muted">
          This will remove {patient.full_name} from your patient list. This can&apos;t be undone.
        </p>
        {deleteError && <p className="text-[13px] text-high-risk font-medium mt-2">{deleteError}</p>}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="secondary" onClick={() => setIsDeleteOpen(false)}>
            Cancel
          </Button>
          <Button variant="destructive" loading={isDeleting} onClick={handleDeleteConfirm}>
            Delete patient
          </Button>
        </div>
      </Modal>

      <Card>
        <Card.Header
          title="Recent reports"
          action={
            <div className="flex gap-2">
              <Link to={`/patients/${patient.id}/donor-search`}>
                <Button size="sm" variant="secondary">
                  Search compatible donors
                </Button>
              </Link>
              <Link to={`/checks/new?patientId=${patient.id}`}>
                <Button size="sm">New compatibility check</Button>
              </Link>
            </div>
          }
        />
        {reports.length === 0 ? (
          <p className="text-[14px] text-text-muted">No compatibility checks run yet.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {reports.map((report) => {
              const { status, label } = reportBadgeProps(report)
              return (
                <li key={report.id}>
                  <Link
                    to={`/reports/${report.id}`}
                    className="flex items-center justify-between py-2.5 hover:bg-bg -mx-1 px-1 rounded transition-colors"
                  >
                    <span className="text-[14px] text-text-muted">
                      {new Date(report.created_at).toLocaleDateString()}
                    </span>
                    <Badge status={status}>{label}</Badge>
                  </Link>
                </li>
              )
            })}
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

      <ReportFilesCard
        categories={PATIENT_REPORT_CATEGORY_OPTIONS}
        loadState={reportFilesState.state}
        existingFiles={reportFilesState.data}
        onUpload={(category, file) => uploadPatientReportFile(patient.id, category, file)}
        onDelete={(id) => deletePatientReportFile(patient.id, id)}
        onDownload={(id, filename) => downloadPatientReportFile(patient.id, id, filename)}
      />

      <PairDocumentsCard patientId={patient.id} />
    </div>
  )
}
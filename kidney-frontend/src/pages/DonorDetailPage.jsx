// src/pages/DonorDetailPage.jsx
import { useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  getDonor,
  updateDonor,
  deleteDonor,
  getDonorHlaTypings,
  replaceDonorHlaTypings,
  updateDonorStatus,
} from "../api/donors"
import { getPatient } from "../api/patients"
import {
  listDonorReportFiles,
  uploadDonorReportFile,
  deleteDonorReportFile,
  downloadDonorReportFile,
} from "../api/reportFiles"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import Card from "../components/ui/Card"
import Select from "../components/ui/Select"
import Modal from "../components/ui/Modal"
import DonorForm from "../components/domain/donor/DonorForm"
import HlaTypingEditor from "../components/domain/hla/HlaTypingEditor"
import ReportFilesCard from "../components/domain/reportFiles/ReportFilesCard"
import { DONOR_STATUS_OPTIONS, donorStatusBadgeProps } from "../constants/donorStatus"
import { RACE_OPTIONS, SEX_OPTIONS, SMOKING_STATUS_OPTIONS } from "../constants/clinicalEnums"
import { boolToTriState, enumToForm } from "../utils/formValue"

function triStateLabel(value) {
  if (value === true) return "Yes"
  if (value === false) return "No"
  return "Unknown"
}

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label ?? "Unknown"
}

export default function DonorDetailPage() {
  const { donorId } = useParams()
  const navigate = useNavigate()
  const [donor, setDonor] = useState(null)
  const [donorLoadState, setDonorLoadState] = useState("loading")
  const [intendedRecipient, setIntendedRecipient] = useState(null)
  const [hlaState, setHlaState] = useState({ state: "loading", data: [] })
  const [reportFilesState, setReportFilesState] = useState({ state: "loading", data: [] })

  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isSavingEdit, setIsSavingEdit] = useState(false)

  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState("")

  useEffect(() => {
    let cancelled = false

    getDonor(donorId)
      .then((data) => !cancelled && (setDonor(data), setDonorLoadState("loaded")))
      .catch(() => !cancelled && setDonorLoadState("error"))

    getDonorHlaTypings(donorId)
      .then((data) => !cancelled && setHlaState({ state: "loaded", data }))
      .catch(() => !cancelled && setHlaState({ state: "error", data: [] }))

    listDonorReportFiles(donorId)
      .then((data) => !cancelled && setReportFilesState({ state: "loaded", data }))
      .catch(() => !cancelled && setReportFilesState({ state: "error", data: [] }))

    return () => {
      cancelled = true
    }
  }, [donorId])

  useEffect(() => {
    if (!donor?.intended_recipient_id) {
      setIntendedRecipient(null)
      return
    }
    let cancelled = false
    getPatient(donor.intended_recipient_id)
      .then((data) => !cancelled && setIntendedRecipient(data))
      .catch(() => !cancelled && setIntendedRecipient(null))
    return () => {
      cancelled = true
    }
  }, [donor?.intended_recipient_id])

  if (donorLoadState === "loading") {
    return (
      <div className="flex justify-center py-16">
        <div className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin" role="status" aria-label="Loading" />
      </div>
    )
  }

  if (donorLoadState === "error" || !donor) {
    return <p className="text-[15px] text-text-muted">Couldn't load this donor.</p>
  }

  async function handleStatusChange(event) {
    const status = event.target.value
    const updated = await updateDonorStatus(donor.id, status)
    setDonor(updated)
  }

  async function handleEditSubmit(payload) {
    setIsSavingEdit(true)
    try {
      const updated = await updateDonor(donor.id, payload)
      setDonor(updated)
      setIsEditOpen(false)
    } finally {
      setIsSavingEdit(false)
    }
  }

  async function handleDeleteConfirm() {
    setDeleteError("")
    setIsDeleting(true)
    try {
      await deleteDonor(donor.id)
      navigate("/donors")
    } catch (err) {
      setDeleteError(err.message || "Couldn't delete this donor. Please try again.")
    } finally {
      setIsDeleting(false)
    }
  }

  const { status: badgeStatus, label: badgeLabel } = donorStatusBadgeProps(donor.status)

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-[22px] font-bold text-text">{donor.full_name}</h1>
            <Badge status="neutral">{donor.blood_type}</Badge>
            <Badge status={badgeStatus}>{badgeLabel}</Badge>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setIsEditOpen(true)}>
              Edit details
            </Button>
            <Button variant="destructive" size="sm" onClick={() => setIsDeleteOpen(true)}>
              Delete donor
            </Button>
          </div>
        </div>
        <p className="text-[14px] text-text-muted">
          {donor.nic_number || "No NIC on file"} · DOB {donor.date_of_birth}
        </p>
      </div>

      <Modal open={isEditOpen} onClose={() => setIsEditOpen(false)} title="Edit donor details">
        <DonorForm
          mode="edit"
          submitLabel="Save changes"
          isSubmitting={isSavingEdit}
          initialValues={{
            fullName: donor.full_name,
            dateOfBirth: donor.date_of_birth,
            bloodType: donor.blood_type,
            rhFactor: donor.rh_factor,
            nicNumber: donor.nic_number || "",
            egfr: donor.egfr ?? "",
            systolicBp: donor.systolic_bp ?? "",
            diastolicBp: donor.diastolic_bp ?? "",
            bmi: donor.bmi ?? "",
            hasDiabetes: boolToTriState(donor.has_diabetes),
            sex: enumToForm(donor.sex),
            race: enumToForm(donor.race),
            smokingStatus: enumToForm(donor.smoking_status),
            creatinine: donor.creatinine ?? "",
            urineAcr: donor.urine_acr ?? "",
            isOnAntihypertensiveMedication: boolToTriState(donor.is_on_antihypertensive_medication),
            familyHistoryKidneyDisease: boolToTriState(donor.family_history_kidney_disease),
            intendedRecipientId: donor.intended_recipient_id || "",
          }}
          onSubmit={handleEditSubmit}
        />
      </Modal>

      <Modal
        open={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        title={`Delete ${donor.full_name}?`}
      >
        <p className="text-[15px] text-text-muted">
          This will remove {donor.full_name} from your donor list and cross-hospital search. This
          can&apos;t be undone.
        </p>
        {deleteError && <p className="text-[13px] text-high-risk font-medium mt-2">{deleteError}</p>}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="secondary" onClick={() => setIsDeleteOpen(false)}>
            Cancel
          </Button>
          <Button variant="destructive" loading={isDeleting} onClick={handleDeleteConfirm}>
            Delete donor
          </Button>
        </div>
      </Modal>

      {donor.intended_recipient_id && (
        <div className="rounded-lg border border-border bg-surface px-4 py-3 text-[14px]">
          <p className="text-text-muted">Intended recipient</p>
          <p className="text-text font-medium">
            {intendedRecipient ? intendedRecipient.full_name : "Loading…"} — not shown in other
            hospitals' cross-hospital searches while this is set.
          </p>
        </div>
      )}

      <Select
        label="Availability status"
        value={donor.status}
        onChange={handleStatusChange}
        options={DONOR_STATUS_OPTIONS}
        helperText="Only 'Available' donors with no intended recipient are visible to other doctors' cross-hospital searches."
      />

      <Card>
        <Card.Header
          title="Clinical suitability"
          subtitle="Not used by the automated compatibility check — feeds the donor safety assessment instead. Edit via 'Edit details'."
          action={
            <Link to={`/donors/${donor.id}/safety-assessment`}>
              <Button size="sm" variant="secondary">
                Run safety assessment
              </Button>
            </Link>
          }
        />
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-3 text-[14px]">
          <div>
            <p className="text-text-muted">Sex</p>
            <p className="text-text font-medium">{optionLabel(SEX_OPTIONS, donor.sex)}</p>
          </div>
          <div>
            <p className="text-text-muted">Race</p>
            <p className="text-text font-medium">{optionLabel(RACE_OPTIONS, donor.race)}</p>
          </div>
          <div>
            <p className="text-text-muted">eGFR</p>
            <p className="text-text font-medium tabular-nums">
              {donor.egfr != null ? `${donor.egfr} mL/min/1.73m²` : "—"}
            </p>
          </div>
          <div>
            <p className="text-text-muted">Creatinine</p>
            <p className="text-text font-medium tabular-nums">
              {donor.creatinine != null ? `${donor.creatinine} mg/dL` : "—"}
            </p>
          </div>
          <div>
            <p className="text-text-muted">Urine ACR</p>
            <p className="text-text font-medium tabular-nums">
              {donor.urine_acr != null ? `${donor.urine_acr} mg/g` : "—"}
            </p>
          </div>
          <div>
            <p className="text-text-muted">Blood pressure</p>
            <p className="text-text font-medium tabular-nums">
              {donor.systolic_bp != null && donor.diastolic_bp != null
                ? `${donor.systolic_bp}/${donor.diastolic_bp} mmHg`
                : "—"}
            </p>
          </div>
          <div>
            <p className="text-text-muted">On antihypertensive medication</p>
            <p className="text-text font-medium">
              {triStateLabel(donor.is_on_antihypertensive_medication)}
            </p>
          </div>
          <div>
            <p className="text-text-muted">BMI</p>
            <p className="text-text font-medium tabular-nums">
              {donor.bmi != null ? `${donor.bmi} kg/m²` : "—"}
            </p>
          </div>
          <div>
            <p className="text-text-muted">Diabetes</p>
            <p className="text-text font-medium">{triStateLabel(donor.has_diabetes)}</p>
          </div>
          <div>
            <p className="text-text-muted">Smoking</p>
            <p className="text-text font-medium">
              {optionLabel(SMOKING_STATUS_OPTIONS, donor.smoking_status)}
            </p>
          </div>
          <div>
            <p className="text-text-muted">Family history of kidney disease</p>
            <p className="text-text font-medium">
              {triStateLabel(donor.family_history_kidney_disease)}
            </p>
          </div>
        </div>
      </Card>

      <HlaTypingEditor
        loadState={hlaState.state}
        initialEntries={hlaState.data}
        onSave={(entries) => replaceDonorHlaTypings(donor.id, entries)}
      />

      <ReportFilesCard
        loadState={reportFilesState.state}
        existingFiles={reportFilesState.data}
        onUpload={(category, file) => uploadDonorReportFile(donor.id, category, file)}
        onDelete={(id) => deleteDonorReportFile(donor.id, id)}
        onDownload={(id, filename) => downloadDonorReportFile(donor.id, id, filename)}
      />
    </div>
  )
}
// src/pages/DetailsStep.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { BLOOD_TYPE_OPTIONS, RH_FACTOR_OPTIONS } from "../constants/clinicalEnums"
import Card from "../components/ui/Card"
import InputField from "../components/ui/InputField"
import SegmentedControl from "../components/ui/SegmentedControl"
import Button from "../components/ui/Button"
import ToggleSwitch from "../components/ui/ToggleSwitch"

function validatePerson(details) {
  const errors = {}
  if (!details.full_name.trim()) errors.full_name = "Full name is required"
  if (!details.date_of_birth) errors.date_of_birth = "Date of birth is required"
  if (!details.blood_type) errors.blood_type = "Blood group is required"
  if (!details.rh_factor) errors.rh_factor = "Rh factor is required"
  return errors
}

// E3.6: blood_type/rh_factor are permanent once set (PatientUpdate/
// DonorUpdate don't even accept them -- see compatibilityWizard.js's
// buildPatientUpdatePayload/buildDonorUpdatePayload). If OCR (or a
// doctor's own edit) leaves `details` disagreeing with the linked record's
// original blood type, silently dropping the disagreement on submit would
// be the worst available failure mode here -- the check would run against
// the record's real blood type while displaying whatever `details` says,
// with no visible link between the two. Compared against `record` (the
// snapshot SubjectStep.jsx took at selection time), not against `details`
// itself, since `details` is exactly the field that may have just changed.
function bloodTypeConflict(details, record) {
  if (!record) return null
  if (!details.blood_type || !details.rh_factor) return null
  if (details.blood_type === record.blood_type && details.rh_factor === record.rh_factor) {
    return null
  }
  return {
    documentValue: `${details.blood_type}${details.rh_factor}`,
    recordValue: `${record.blood_type}${record.rh_factor}`,
  }
}

function PersonDetailsCard({ title, subtitle, details, onChange, errors }) {
  function updateField(field) {
    return (e) => onChange({ [field]: e.target.value })
  }

  return (
    <Card>
      <Card.Header title={title} subtitle={subtitle} />
      <div className="flex flex-col gap-4">
        <InputField
          label="Full name"
          value={details.full_name}
          onChange={updateField("full_name")}
          error={errors.full_name}
          required
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <InputField
            label="Date of birth"
            type="date"
            value={details.date_of_birth}
            onChange={updateField("date_of_birth")}
            error={errors.date_of_birth}
            required
          />
          <SegmentedControl
            label="Blood group"
            options={BLOOD_TYPE_OPTIONS}
            value={details.blood_type}
            onChange={(value) => onChange({ blood_type: value })}
            error={errors.blood_type}
            required
          />
          <SegmentedControl
            label="Rh factor"
            options={RH_FACTOR_OPTIONS}
            value={details.rh_factor}
            onChange={(value) => onChange({ rh_factor: value })}
            error={errors.rh_factor}
            required
          />
        </div>
        <InputField
          label="NIC number"
          helperText="Optional"
          value={details.nic_number}
          onChange={updateField("nic_number")}
        />
      </div>
    </Card>
  )
}

export default function DetailsStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  const [patientErrors, setPatientErrors] = useState({})
  const [donorErrors, setDonorErrors] = useState({})
  const [verificationError, setVerificationError] = useState(false)

  // Unlike HlaTypingStep/BeadSpecificityStep, person-details isn't owned by
  // one fixed document type -- PersonDetailsOcr is merged from whichever
  // document(s) actually get uploaded (see api/compatibilityWizard.js's
  // buildPersonPayload). So "was this OCR-extracted" here means "did any
  // document finish OCR", not one specific document_type.
  const wasOcrExtracted = Object.values(state.extraction?.documents ?? {}).some(
    (doc) => doc?.status === "done"
  )

  const patientBloodConflict = bloodTypeConflict(
    state.patient_details,
    state.subject.patientRecord
  )
  const donorBloodConflict = bloodTypeConflict(state.donor_details, state.subject.donorRecord)

  function handleContinue() {
    const nextPatientErrors = validatePerson(state.patient_details)
    const nextDonorErrors = validatePerson(state.donor_details)
    setPatientErrors(nextPatientErrors)
    setDonorErrors(nextDonorErrors)

    const hasErrors =
      Object.keys(nextPatientErrors).length > 0 ||
      Object.keys(nextDonorErrors).length > 0

    const needsVerification = wasOcrExtracted && !state.ocr_verified?.details

    setVerificationError(needsVerification)

    if (hasErrors || needsVerification || patientBloodConflict || donorBloodConflict) return

    actions.unlockStep(3)
    navigate("/checks/new/hla")
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Patient &amp; donor details</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Confirm both identities before typing data is entered against them.
        </p>
      </div>

      <PersonDetailsCard
        title="Patient"
        subtitle="The transplant recipient"
        details={state.patient_details}
        errors={patientErrors}
        onChange={(patch) => actions.setPatientDetails(patch)}
      />
      {patientBloodConflict && (
        <div className="rounded-md border border-high-risk bg-high-risk-subtle p-4 -mt-2">
          <p className="text-[13px] font-medium text-high-risk">
            This reads blood group {patientBloodConflict.documentValue}, but this patient's record
            says {patientBloodConflict.recordValue}. One of them is wrong. Blood group is permanent
            once set — resolve this on the patient's own record before running the check.
          </p>
        </div>
      )}

      <PersonDetailsCard
        title="Donor"
        subtitle="The prospective kidney donor"
        details={state.donor_details}
        errors={donorErrors}
        onChange={(patch) => actions.setDonorDetails(patch)}
      />
      {donorBloodConflict && (
        <div className="rounded-md border border-high-risk bg-high-risk-subtle p-4 -mt-2">
          <p className="text-[13px] font-medium text-high-risk">
            This reads blood group {donorBloodConflict.documentValue}, but this donor's record says{" "}
            {donorBloodConflict.recordValue}. One of them is wrong. Blood group is permanent once
            set — resolve this on the donor's own record before running the check.
          </p>
        </div>
      )}

      {wasOcrExtracted && (
        <div
          className={[
            "rounded-md border p-4",
            verificationError ? "border-high-risk bg-high-risk-subtle" : "border-moderate bg-moderate-subtle",
          ].join(" ")}
        >
          <ToggleSwitch
            label="I have reviewed these names, dates of birth, and blood groups against the source document"
            helperText="This data was extracted by AI from an uploaded photo — confirm it's accurate before continuing."
            checked={!!state.ocr_verified?.details}
            onChange={(checked) => {
              actions.setOcrVerified("details", checked)
              if (checked) setVerificationError(false)
            }}
          />
          {verificationError && (
            <p className="text-[13px] text-high-risk font-medium mt-2">
              Confirm this before continuing — the compatibility check refuses to run on
              unverified OCR data, and blood type is permanent once set on a record.
            </p>
          )}
        </div>
      )}

      <div className="flex items-center justify-between">
        <Button variant="secondary" onClick={() => navigate("/checks/new/photos")}>
          Back
        </Button>
        <Button size="lg" onClick={handleContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}
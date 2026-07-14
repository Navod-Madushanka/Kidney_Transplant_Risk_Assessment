// src/pages/DetailsStep.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { BLOOD_TYPE_OPTIONS } from "../constants/clinicalEnums"
import Card from "../components/ui/Card"
import InputField from "../components/ui/InputField"
import SegmentedControl from "../components/ui/SegmentedControl"
import Button from "../components/ui/Button"

function validatePerson(details) {
  const errors = {}
  if (!details.full_name.trim()) errors.full_name = "Full name is required"
  if (!details.date_of_birth) errors.date_of_birth = "Date of birth is required"
  if (!details.blood_type) errors.blood_type = "Blood group is required"
  return errors
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

  function handleContinue() {
    const nextPatientErrors = validatePerson(state.patient_details)
    const nextDonorErrors = validatePerson(state.donor_details)
    setPatientErrors(nextPatientErrors)
    setDonorErrors(nextDonorErrors)

    const hasErrors =
      Object.keys(nextPatientErrors).length > 0 ||
      Object.keys(nextDonorErrors).length > 0

    if (hasErrors) return

    actions.unlockStep(2)
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

      <PersonDetailsCard
        title="Donor"
        subtitle="The prospective kidney donor"
        details={state.donor_details}
        errors={donorErrors}
        onChange={(patch) => actions.setDonorDetails(patch)}
      />

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
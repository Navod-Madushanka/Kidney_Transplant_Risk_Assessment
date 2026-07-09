// src/components/domain/patient/PatientForm.jsx
import { useState } from "react"
import InputField from "../../ui/InputField"
import Select from "../../ui/Select"
import Button from "../../ui/Button"
import { BLOOD_TYPE_OPTIONS } from "../../../constants/clinicalEnums"

const emptyForm = { fullName: "", dateOfBirth: "", bloodType: "", nicNumber: "" }

/**
 * Usage:
 *   <PatientForm onSubmit={handleCreatePatient} isSubmitting={isSaving} submitLabel="Add patient" />
 *
 * onSubmit receives a payload shaped exactly for PatientCreate:
 *   { full_name, date_of_birth, blood_type, nic_number }
 */
export default function PatientForm({
  onSubmit,
  isSubmitting = false,
  submitLabel = "Save patient",
  initialValues,
}) {
  const [form, setForm] = useState({ ...emptyForm, ...initialValues })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState("")

  function updateField(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  function validate() {
    const next = {}
    if (!form.fullName.trim()) next.fullName = "Full name is required"
    if (!form.dateOfBirth) next.dateOfBirth = "Date of birth is required"
    if (!form.bloodType) next.bloodType = "Blood group is required"
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError("")
    if (!validate()) return

    try {
      await onSubmit({
        full_name: form.fullName.trim(),
        date_of_birth: form.dateOfBirth,
        blood_type: form.bloodType,
        nic_number: form.nicNumber.trim() || null,
      })
    } catch (err) {
      setFormError(err.message || "Couldn't save this patient. Please try again.")
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <InputField
        label="Full name"
        value={form.fullName}
        onChange={updateField("fullName")}
        error={errors.fullName}
        required
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <InputField
          label="Date of birth"
          type="date"
          value={form.dateOfBirth}
          onChange={updateField("dateOfBirth")}
          error={errors.dateOfBirth}
          required
        />
        <Select
          label="Blood group"
          placeholder="Select blood group"
          options={BLOOD_TYPE_OPTIONS}
          value={form.bloodType}
          onChange={updateField("bloodType")}
          error={errors.bloodType}
          required
        />
      </div>
      <InputField
        label="NIC number"
        helperText="Optional"
        value={form.nicNumber}
        onChange={updateField("nicNumber")}
      />

      {formError && (
        <p role="alert" className="text-[13px] text-high-risk font-medium">
          {formError}
        </p>
      )}

      <Button type="submit" loading={isSubmitting} className="self-start mt-2">
        {submitLabel}
      </Button>
    </form>
  )
}
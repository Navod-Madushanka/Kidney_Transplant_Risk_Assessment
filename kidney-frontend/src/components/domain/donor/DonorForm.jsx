import { useState } from "react"
import InputField from "../../ui/InputField"
import SegmentedControl from "../../ui/SegmentedControl"
import Button from "../../ui/Button"
import { BLOOD_TYPE_OPTIONS, RH_FACTOR_OPTIONS } from "../../../constants/clinicalEnums"

const emptyForm = { fullName: "", dateOfBirth: "", bloodType: "", rhFactor: "", nicNumber: "" }

/**
 * Usage:
 *   <DonorForm onSubmit={handleCreateDonor} isSubmitting={isSaving} submitLabel="Add donor" />
 *
 * Pass mode="edit" to update an existing donor instead of creating one:
 * blood group/Rh factor are shown but locked (they're permanent once set —
 * the compatibility engine and existing reports trust them), and the
 * onSubmit payload omits them, matching DonorUpdate.
 */
export default function DonorForm({
  onSubmit,
  isSubmitting = false,
  submitLabel = "Save donor",
  initialValues,
  mode = "create",
}) {
  const [form, setForm] = useState({ ...emptyForm, ...initialValues })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState("")
  const isEdit = mode === "edit"

  function updateField(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  function updateValue(field) {
    return (value) => setForm((prev) => ({ ...prev, [field]: value }))
  }

  function validate() {
    const next = {}
    if (!form.fullName.trim()) next.fullName = "Full name is required"
    if (!form.dateOfBirth) next.dateOfBirth = "Date of birth is required"
    if (!isEdit) {
      if (!form.bloodType) next.bloodType = "Blood group is required"
      if (!form.rhFactor) next.rhFactor = "Rh factor is required"
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError("")
    if (!validate()) return

    const payload = {
      full_name: form.fullName.trim(),
      date_of_birth: form.dateOfBirth,
      nic_number: form.nicNumber.trim() || null,
    }
    if (!isEdit) {
      payload.blood_type = form.bloodType
      payload.rh_factor = form.rhFactor
    }

    try {
      await onSubmit(payload)
    } catch (err) {
      setFormError(err.message || "Couldn't save this donor. Please try again.")
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
        <SegmentedControl
          label="Blood group"
          options={BLOOD_TYPE_OPTIONS}
          value={form.bloodType}
          onChange={updateValue("bloodType")}
          error={errors.bloodType}
          required={!isEdit}
          disabled={isEdit}
          helperText={isEdit ? "Locked after creation" : undefined}
        />
        <SegmentedControl
          label="Rh factor"
          options={RH_FACTOR_OPTIONS}
          value={form.rhFactor}
          onChange={updateValue("rhFactor")}
          error={errors.rhFactor}
          required={!isEdit}
          disabled={isEdit}
          helperText={isEdit ? "Locked after creation" : undefined}
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
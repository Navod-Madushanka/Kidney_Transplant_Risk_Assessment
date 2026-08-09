import { useEffect, useState } from "react"
import InputField from "../../ui/InputField"
import SegmentedControl from "../../ui/SegmentedControl"
import Select from "../../ui/Select"
import Button from "../../ui/Button"
import { BLOOD_TYPE_OPTIONS, RH_FACTOR_OPTIONS } from "../../../constants/clinicalEnums"
import { listPatients } from "../../../api/patients"

const emptyForm = {
  fullName: "",
  dateOfBirth: "",
  bloodType: "",
  rhFactor: "",
  nicNumber: "",
  egfr: "",
  systolicBp: "",
  diastolicBp: "",
  bmi: "",
  hasDiabetes: "unknown",
  isSmoker: "unknown",
  intendedRecipientId: "",
}

// has_diabetes/is_smoker are nullable booleans on the backend (unknown/no/
// yes), not a plain checkbox — an unassessed donor shouldn't default to a
// confirmed "no". These convert between that tri-state and the form's
// string-valued SegmentedControl.
const TRI_STATE_OPTIONS = [
  { value: "unknown", label: "Unknown" },
  { value: "no", label: "No" },
  { value: "yes", label: "Yes" },
]

function boolToTriState(value) {
  if (value === true) return "yes"
  if (value === false) return "no"
  return "unknown"
}

function triStateToBool(value) {
  if (value === "yes") return true
  if (value === "no") return false
  return null
}

function numberOrNull(value) {
  return value === "" ? null : Number(value)
}

/**
 * Usage:
 *   <DonorForm onSubmit={handleCreateDonor} isSubmitting={isSaving} submitLabel="Add donor" />
 *
 * Pass mode="edit" to update an existing donor instead of creating one:
 * blood group/Rh factor are shown but locked (they're permanent once set —
 * the compatibility engine and existing reports trust them), and the
 * onSubmit payload omits them, matching DonorUpdate. Clinical fields
 * (eGFR/BP/BMI/diabetes/smoking) are the opposite — expected to change over
 * a donor's workup — so they're always editable in both modes.
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
  const [patients, setPatients] = useState([])
  const [patientsLoadState, setPatientsLoadState] = useState("loading")
  const isEdit = mode === "edit"

  useEffect(() => {
    let cancelled = false
    listPatients()
      .then((data) => !cancelled && (setPatients(data), setPatientsLoadState("loaded")))
      .catch(() => !cancelled && setPatientsLoadState("error"))
    return () => {
      cancelled = true
    }
  }, [])

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
      egfr: numberOrNull(form.egfr),
      systolic_bp: numberOrNull(form.systolicBp),
      diastolic_bp: numberOrNull(form.diastolicBp),
      bmi: numberOrNull(form.bmi),
      has_diabetes: triStateToBool(form.hasDiabetes),
      is_smoker: triStateToBool(form.isSmoker),
      intended_recipient_id: form.intendedRecipientId || null,
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
      <Select
        label="Intended recipient"
        placeholder={patientsLoadState === "loading" ? "Loading…" : "None — available for general pool"}
        disabled={patientsLoadState === "loading"}
        options={patients.map((p) => ({
          value: p.id,
          label: `${p.full_name} — ${p.nic_number || "no NIC"}`,
        }))}
        value={form.intendedRecipientId}
        onChange={updateField("intendedRecipientId")}
        helperText={
          patientsLoadState === "error"
            ? "Couldn't load your patients."
            : "If this donor is only donating for one of your patients, select them here — they won't appear in other hospitals' searches. Leave blank for an altruistic/deceased donor."
        }
      />

      <div className="pt-2 border-t border-border">
        <p className="text-[13px] font-semibold text-text-muted mb-3">
          Clinical suitability (reference only — not used by the automated compatibility check)
        </p>
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <InputField
              label="eGFR"
              type="number"
              step="0.01"
              min="0"
              max="200"
              helperText="mL/min/1.73m²"
              value={form.egfr}
              onChange={updateField("egfr")}
            />
            <InputField
              label="Systolic BP"
              type="number"
              min="50"
              max="300"
              helperText="mmHg"
              value={form.systolicBp}
              onChange={updateField("systolicBp")}
            />
            <InputField
              label="Diastolic BP"
              type="number"
              min="30"
              max="200"
              helperText="mmHg"
              value={form.diastolicBp}
              onChange={updateField("diastolicBp")}
            />
          </div>
          <InputField
            label="BMI"
            type="number"
            step="0.1"
            min="0"
            max="100"
            helperText="kg/m²"
            className="max-w-50"
            value={form.bmi}
            onChange={updateField("bmi")}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SegmentedControl
              label="Diabetes"
              options={TRI_STATE_OPTIONS}
              value={form.hasDiabetes}
              onChange={updateValue("hasDiabetes")}
            />
            <SegmentedControl
              label="Smoker"
              options={TRI_STATE_OPTIONS}
              value={form.isSmoker}
              onChange={updateValue("isSmoker")}
            />
          </div>
        </div>
      </div>

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
import { useEffect, useState } from "react"
import InputField from "../../ui/InputField"
import SegmentedControl from "../../ui/SegmentedControl"
import Select from "../../ui/Select"
import Button from "../../ui/Button"
import {
  BLOOD_TYPE_OPTIONS,
  RACE_OPTIONS,
  RH_FACTOR_OPTIONS,
  SEX_OPTIONS,
  SMOKING_STATUS_OPTIONS,
} from "../../../constants/clinicalEnums"
import { listPatients } from "../../../api/patients"
import {
  TRI_STATE_OPTIONS,
  formToEnum,
  numberOrNull,
  triStateToBool,
  withUnknownOption,
} from "../../../utils/formValue"

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
  sex: "unknown",
  race: "unknown",
  smokingStatus: "unknown",
  creatinine: "",
  urineAcr: "",
  isOnAntihypertensiveMedication: "unknown",
  familyHistoryKidneyDisease: "unknown",
  weightKg: "",
  isBiologicallyRelated: "unknown",
  intendedRecipientId: "",
}

/**
 * Usage:
 *   <DonorForm onSubmit={handleCreateDonor} isSubmitting={isSaving} submitLabel="Add donor" />
 *
 * Pass mode="edit" to update an existing donor instead of creating one:
 * blood group/RhD type are shown but locked (they're permanent once set —
 * the compatibility engine and existing reports trust them), and the
 * onSubmit payload omits them, matching DonorUpdate. The clinical/safety-
 * assessment fields below them (eGFR/BP/BMI/creatinine/urine ACR/diabetes/
 * smoking/sex/race/antihypertensive medication/family history) are the
 * opposite — expected to change over a donor's workup — so they're always
 * editable in both modes.
 *
 * hideIntendedRecipientPicker: for NewPairPage.jsx, where the patient this
 * donor is being registered for doesn't exist yet at donor-form-render
 * time -- the picker could only ever show "None" there, and whatever it
 * held would be silently overridden by POST /pairs setting
 * intended_recipient_id to the newly-created patient anyway. Skips the
 * listPatients() fetch too, not just the render.
 */
export default function DonorForm({
  onSubmit,
  isSubmitting = false,
  submitLabel = "Save donor",
  initialValues,
  mode = "create",
  hideIntendedRecipientPicker = false,
}) {
  const [form, setForm] = useState({ ...emptyForm, ...initialValues })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState("")
  const [patients, setPatients] = useState([])
  const [patientsLoadState, setPatientsLoadState] = useState("loading")
  const isEdit = mode === "edit"

  useEffect(() => {
    if (hideIntendedRecipientPicker) return
    let cancelled = false
    listPatients()
      .then((data) => !cancelled && (setPatients(data), setPatientsLoadState("loaded")))
      .catch(() => !cancelled && setPatientsLoadState("error"))
    return () => {
      cancelled = true
    }
  }, [hideIntendedRecipientPicker])

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
      if (!form.rhFactor) next.rhFactor = "RhD type is required"
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
      sex: formToEnum(form.sex),
      race: formToEnum(form.race),
      smoking_status: formToEnum(form.smokingStatus),
      creatinine: numberOrNull(form.creatinine),
      urine_acr: numberOrNull(form.urineAcr),
      is_on_antihypertensive_medication: triStateToBool(form.isOnAntihypertensiveMedication),
      family_history_kidney_disease: triStateToBool(form.familyHistoryKidneyDisease),
      weight_kg: numberOrNull(form.weightKg),
      is_biologically_related: triStateToBool(form.isBiologicallyRelated),
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
          label="RhD type"
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
      {!hideIntendedRecipientPicker && (
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
      )}

      <div className="pt-2 border-t border-border">
        <p className="text-[13px] font-semibold text-text-muted mb-3">
          Clinical suitability &amp; donor safety assessment (not used by the automated
          compatibility check — feeds the separate donor safety assessment instead)
        </p>
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SegmentedControl
              label="Sex"
              options={withUnknownOption(SEX_OPTIONS)}
              value={form.sex}
              onChange={updateValue("sex")}
            />
            <SegmentedControl
              label="Race"
              options={withUnknownOption(RACE_OPTIONS)}
              value={form.race}
              onChange={updateValue("race")}
              helperText="For the safety-assessment risk model only — see that screen for why this matters"
            />
          </div>
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
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <InputField
              label="BMI"
              type="number"
              step="0.1"
              min="0"
              max="100"
              helperText="kg/m²"
              value={form.bmi}
              onChange={updateField("bmi")}
            />
            <InputField
              label="Creatinine"
              type="number"
              step="0.01"
              min="0"
              max="30"
              helperText="mg/dL — raw lab value, informational only"
              value={form.creatinine}
              onChange={updateField("creatinine")}
            />
            <InputField
              label="Urine ACR"
              type="number"
              step="0.01"
              min="0"
              helperText="mg/g — albumin-to-creatinine ratio"
              value={form.urineAcr}
              onChange={updateField("urineAcr")}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SegmentedControl
              label="Diabetes"
              options={TRI_STATE_OPTIONS}
              value={form.hasDiabetes}
              onChange={updateValue("hasDiabetes")}
            />
            <SegmentedControl
              label="Smoking"
              options={withUnknownOption(SMOKING_STATUS_OPTIONS)}
              value={form.smokingStatus}
              onChange={updateValue("smokingStatus")}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SegmentedControl
              label="On antihypertensive medication"
              options={TRI_STATE_OPTIONS}
              value={form.isOnAntihypertensiveMedication}
              onChange={updateValue("isOnAntihypertensiveMedication")}
            />
            <SegmentedControl
              label="Family history of kidney disease"
              options={TRI_STATE_OPTIONS}
              value={form.familyHistoryKidneyDisease}
              onChange={updateValue("familyHistoryKidneyDisease")}
            />
          </div>
        </div>
      </div>

      <div className="pt-2 border-t border-border">
        <p className="text-[13px] font-semibold text-text-muted mb-3">
          LKDPI inputs (donor side, in addition to eGFR/BMI/BP/smoking above) — used only for the
          living-donor compatibility score, not the compatibility check itself
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <InputField
            label="Weight"
            type="number"
            step="0.01"
            min="0"
            max="400"
            helperText="kg — needed alongside recipient weight for the donor/recipient weight ratio"
            value={form.weightKg}
            onChange={updateField("weightKg")}
          />
          <SegmentedControl
            label="Biologically related to recipient"
            options={TRI_STATE_OPTIONS}
            value={form.isBiologicallyRelated}
            onChange={updateValue("isBiologicallyRelated")}
          />
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
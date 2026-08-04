// src/pages/ReviewStep.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { submitCompatibilityCheck } from "../api/compatibilityWizard"
import { SENSITIZATION_EVENT_OPTIONS, HLA_LOCUS_OPTIONS } from "../constants/clinicalEnums"
import Card from "../components/ui/Card"
import Table from "../components/ui/Table"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import SegmentedControl from "../components/ui/SegmentedControl"
import InputField from "../components/ui/InputField"

// Step 6 of the backend pipeline (see app/services/crossmatch_service.py) —
// is_positive is the only field that actually gates anything; positive =
// reject, negative = proceed. This is standard clinical convention, not a
// judgment call the doctors needed to weigh in on.
const CROSSMATCH_RESULT_OPTIONS = [
  { value: "negative", label: "Negative" },
  { value: "positive", label: "Positive" },
]

const SUBMISSION_STEPS = [
  { key: "patientId", label: "Creating patient record" },
  { key: "donorId", label: "Creating donor record" },
  { key: "patientHlaDone", label: "Saving patient HLA typing" },
  { key: "donorHlaDone", label: "Saving donor HLA typing" },
  { key: "antibodyProfilesDone", label: "Saving antibody profile" },
  { key: "sensitizationDone", label: "Saving sensitization events" },
  { key: "reportId", label: "Running compatibility check" },
]

function findMissingSensitizationDates(sensitization, sensitizationDates) {
  return SENSITIZATION_EVENT_OPTIONS.filter(
    (option) => sensitization[option.value] && !sensitizationDates[option.value]
  ).map((option) => option.label)
}

function PersonSummary({ title, details }) {
  return (
    <div>
      <p className="text-[13px] font-semibold text-text-muted mb-1.5">{title}</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[14px]">
        <span className="text-text-muted">Full name</span>
        <span className="text-text font-medium">{details.full_name || "—"}</span>
        <span className="text-text-muted">Date of birth</span>
        <span className="text-text font-medium">{details.date_of_birth || "—"}</span>
        <span className="text-text-muted">Blood group</span>
        <span className="text-text font-medium">
          {details.blood_type ? `${details.blood_type}${details.rh_factor || ""}` : "—"}
        </span>
        <span className="text-text-muted">NIC number</span>
        <span className="text-text font-medium">{details.nic_number || "No NIC on file"}</span>
      </div>
    </div>
  )
}

function HlaSummaryTable({ patientHla, donorHla }) {
  const rows = HLA_LOCUS_OPTIONS.map((option) => {
    const patientRow = patientHla.find((row) => row.locus === option.value)
    const donorRow = donorHla.find((row) => row.locus === option.value)
    return {
      locusLabel: option.label,
      patientAlleles: `${patientRow.allele_1 || "—"}, ${patientRow.allele_2 || "—"}`,
      donorAlleles: `${donorRow.allele_1 || "—"}, ${donorRow.allele_2 || "—"}`,
    }
  })

  return (
    <Table
      columns={[
        { key: "locusLabel", label: "Locus" },
        { key: "patientAlleles", label: "Patient" },
        { key: "donorAlleles", label: "Donor" },
      ]}
      rows={rows}
      getRowId={(row) => row.locusLabel}
    />
  )
}

export default function ReviewStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  const [progress, setProgress] = useState({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [validationError, setValidationError] = useState(null)

  const uploadedDocumentCount = Object.values(state.photos).filter(Boolean).length
  const completedStepCount = SUBMISSION_STEPS.filter((step) => progress[step.key]).length

  async function handleSubmit() {
    setValidationError(null)
    setSubmitError(null)

    const missingDates = findMissingSensitizationDates(
      state.sensitization,
      state.sensitization_dates
    )
    if (missingDates.length > 0) {
      setValidationError(
        `Enter a date for: ${missingDates.join(", ")} — go back to Sensitization to fill these in.`
      )
      return
    }

    if (state.crossmatch.is_positive === null) {
      setValidationError(
        "Confirm the crossmatch result (Negative or Positive) below before running the check."
      )
      return
    }

    setIsSubmitting(true)
    try {
      const report = await submitCompatibilityCheck(state, progress, setProgress)
      actions.reset()
      navigate(`/reports/${report.id}`, { replace: true })
    } catch (err) {
      setProgress(err.progress ?? progress)
      setSubmitError(err.message || "Submission failed partway through. You can retry safely.")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Review &amp; submit</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Confirm everything below, then run the compatibility check.
        </p>
      </div>

      <Card>
        <Card.Header title="Patient &amp; donor" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <PersonSummary title="Patient" details={state.patient_details} />
          <PersonSummary title="Donor" details={state.donor_details} />
        </div>
      </Card>

      <Card>
        <Card.Header title="HLA typing" subtitle="Both alleles, per locus" />
        <HlaSummaryTable patientHla={state.patient_hla} donorHla={state.donor_hla} />
      </Card>

      <Card>
        <Card.Header title="Sensitization" />
        <div className="flex flex-col gap-2">
          {SENSITIZATION_EVENT_OPTIONS.map((option) => {
            const isOn = state.sensitization[option.value]
            return (
              <div key={option.value} className="flex items-center justify-between text-[14px]">
                <span className="text-text">{option.label}</span>
                {isOn ? (
                  <span className="text-text-muted">
                    {state.sensitization_dates[option.value] || "No date entered"}
                  </span>
                ) : (
                  <Badge status="neutral">Not applicable</Badge>
                )}
              </div>
            )
          })}
          <div className="flex items-center justify-between text-[14px] pt-2 mt-1 border-t border-border">
            <span className="text-text-muted">Base MFI cutoff</span>
            <span className="text-text font-semibold tabular-nums">{state.mfi_cutoff}</span>
          </div>
        </div>
      </Card>

      <Card>
        <Card.Header
          title="Bead specificity"
          subtitle={`${state.bead_specificity.length} antigen${state.bead_specificity.length === 1 ? "" : "s"} recorded`}
        />
        {state.bead_specificity.length === 0 ? (
          <p className="text-[14px] text-text-muted">No bead specificity data entered.</p>
        ) : (
          <Table
            columns={[
              { key: "antigen", label: "Antigen" },
              { key: "mfi", label: "MFI", align: "right" },
            ]}
            rows={state.bead_specificity}
            getRowId={(row) => row.antigen}
          />
        )}
      </Card>

      <Card>
        <Card.Header
          title="Crossmatch"
          subtitle="Required — this is Step 6 of the compatibility check and gates the final result"
        />
        <div className="flex flex-col gap-4">
          <SegmentedControl
            label="Crossmatch result"
            required
            options={CROSSMATCH_RESULT_OPTIONS}
            value={
              state.crossmatch.is_positive === null
                ? undefined
                : state.crossmatch.is_positive
                  ? "positive"
                  : "negative"
            }
            onChange={(value) => actions.setCrossmatch({ is_positive: value === "positive" })}
            helperText="A positive crossmatch halts the check — the patient's serum reacted against donor cells."
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <InputField
              label="T-cell result"
              value={state.crossmatch.t_cell_result}
              onChange={(e) => actions.setCrossmatch({ t_cell_result: e.target.value })}
              placeholder="e.g. Negative"
            />
            <InputField
              label="B-cell result"
              value={state.crossmatch.b_cell_result}
              onChange={(e) => actions.setCrossmatch({ b_cell_result: e.target.value })}
              placeholder="e.g. Negative"
            />
          </div>

          <InputField
            label="Remarks"
            value={state.crossmatch.remarks}
            onChange={(e) => actions.setCrossmatch({ remarks: e.target.value })}
            placeholder="Optional — any additional lab notes"
          />
        </div>
      </Card>

      <Card>
        <Card.Header
          title="Uploaded documents"
          subtitle={`${uploadedDocumentCount} of 4 attached`}
        />
        <p className="text-[13px] text-text-muted">
          Documents are for your own reference during this check and aren't sent as part of
          the submission below.
        </p>
      </Card>

      {validationError && (
        <div className="rounded-md border border-high-risk/30 bg-high-risk-subtle p-4">
          <p className="text-[14px] font-semibold text-high-risk">{validationError}</p>
        </div>
      )}

      {submitError && (
        <div className="rounded-md border border-high-risk/30 bg-high-risk-subtle p-4 flex flex-col gap-1">
          <p className="text-[14px] font-semibold text-high-risk">{submitError}</p>
          <p className="text-[13px] text-text-muted">
            {completedStepCount} of {SUBMISSION_STEPS.length} steps completed before this
            happened — retrying will pick up from where it stopped, not start over.
          </p>
        </div>
      )}

      {isSubmitting && (
        <div className="rounded-md border border-border bg-bg p-4">
          <p className="text-[13px] font-semibold text-text-muted">
            {SUBMISSION_STEPS.find((step) => !progress[step.key])?.label ?? "Finishing up"}…
          </p>
        </div>
      )}

      <div className="flex items-center justify-between">
        <Button
          variant="secondary"
          onClick={() => navigate("/checks/new/bead-chart")}
          disabled={isSubmitting}
        >
          Back
        </Button>
        <Button size="lg" onClick={handleSubmit} loading={isSubmitting}>
          {submitError ? "Retry submission" : "Run compatibility check"}
        </Button>
      </div>
    </div>
  )
}
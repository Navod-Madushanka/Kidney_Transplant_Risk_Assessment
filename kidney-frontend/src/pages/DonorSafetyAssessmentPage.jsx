// src/pages/DonorSafetyAssessmentPage.jsx
import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { getDonor } from "../api/donors"
import { getDonorRiskAssessment } from "../api/donorRisk"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import Card from "../components/ui/Card"

function reviewFlagBadge(value) {
  if (value === true) return <Badge status="pending">Present — review</Badge>
  if (value === false) return <Badge status="clear">No</Badge>
  return <Badge status="neutral">Unknown</Badge>
}

// The API reports missing predictors as its own Donor field names (e.g.
// "is_on_antihypertensive_medication") -- readable for a developer, not for
// the doctor reading this screen. Only the fields donor_risk_service.py can
// actually report as missing need an entry here.
const FIELD_LABELS = {
  age_years: "age",
  sex: "sex",
  race: "race",
  egfr: "eGFR",
  systolic_bp: "systolic BP",
  diastolic_bp: "diastolic BP",
  is_on_antihypertensive_medication: "antihypertensive medication use",
  bmi: "BMI",
  has_diabetes: "diabetes",
  urine_acr: "urine ACR",
  smoking_status: "smoking status",
}

function friendlyFieldList(fields) {
  return fields.map((field) => FIELD_LABELS[field] ?? field).join(", ")
}

export default function DonorSafetyAssessmentPage() {
  const { donorId } = useParams()
  const [donor, setDonor] = useState(null)
  const [state, setState] = useState({ status: "loading", data: null })

  useEffect(() => {
    let cancelled = false

    getDonor(donorId).then((data) => !cancelled && setDonor(data))

    getDonorRiskAssessment(donorId)
      .then((data) => !cancelled && setState({ status: "loaded", data }))
      .catch(() => !cancelled && setState({ status: "error", data: null }))

    return () => {
      cancelled = true
    }
  }, [donorId])

  const result = state.data

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      <div>
        <h1 className="text-[22px] font-bold text-text">Donor safety assessment</h1>
        <p className="text-[14px] text-text-muted">
          {donor
            ? `Is it safe for ${donor.full_name} to donate a kidney — assessed on its own, independent of any recipient.`
            : "Loading donor…"}
        </p>
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
          <p className="text-[15px] text-text-muted">
            Couldn't load this donor's safety assessment. Please try refreshing.
          </p>
        </div>
      )}

      {state.status === "loaded" && result && (
        <>
          <p className="text-[12px] text-text-muted">{result.general_disclaimer}</p>

          {!result.population_validated && result.race_extrapolation_disclaimer && (
            <div className="border border-high-risk rounded-lg p-4 bg-high-risk-subtle">
              <p className="text-[14px] font-semibold text-high-risk">
                Extrapolated beyond the model's validated population
              </p>
              <p className="text-[13px] text-high-risk mt-1">
                {result.race_extrapolation_disclaimer}
              </p>
            </div>
          )}

          {!result.has_sufficient_data_for_projection && (
            <div className="border border-border rounded-lg p-8 text-center bg-surface flex flex-col items-center gap-3">
              <p className="text-[15px] text-text-muted">
                Not enough data to project this donor's long-term risk.
              </p>
              <p className="text-[13px] text-text-muted">
                Missing: {friendlyFieldList(result.missing_projection_predictors)}
              </p>
              <Link to={`/donors/${donorId}`}>
                <Button size="sm" variant="secondary">
                  Go to donor details
                </Button>
              </Link>
            </div>
          )}

          {result.has_sufficient_data_for_projection && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <StatTile
                label="15-year projected risk"
                value={`${result.fifteen_year_risk_percent.toFixed(2)}%`}
              />
              <StatTile
                label="Lifetime projected risk"
                value={`${result.lifetime_risk_percent.toFixed(2)}%`}
              />
              <StatTile
                label="Vs. this donor's own healthy baseline"
                value={`${result.relative_risk_multiplier.toFixed(2)}×`}
              />
            </div>
          )}

          <Card>
            <Card.Header
              title="Absolute contraindication screen"
              subtitle="Hard exclusion criteria the model's own authors used to define a low-risk reference population"
            />
            {!result.has_sufficient_data_for_contraindication_screen ? (
              <p className="text-[14px] text-text-muted">
                Not enough data — missing:{" "}
                {friendlyFieldList(result.missing_contraindication_predictors)}
              </p>
            ) : result.has_any_contraindication ? (
              <div className="flex flex-col gap-3">
                {result.contraindications.map((flag) => (
                  <div key={flag} className="flex items-start gap-2">
                    <Badge status="fail">Flagged</Badge>
                    <p className="text-[14px] text-text">{flag}</p>
                  </div>
                ))}
              </div>
            ) : (
              <Badge status="pass">No contraindications found</Badge>
            )}

            <div className="mt-4 pt-4 border-t border-border">
              <p className="text-[13px] text-text-muted mb-1.5">Not assessed by this tool:</p>
              <ul className="list-disc list-inside text-[13px] text-text-muted space-y-0.5">
                {result.contraindication_criteria_not_assessed.map((criterion) => (
                  <li key={criterion}>{criterion}</li>
                ))}
              </ul>
            </div>
          </Card>

          <Card>
            <Card.Header
              title="Clinician review flags"
              subtitle="Not scored by the model — informational, for clinical judgment"
            />
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-[14px] text-text-muted">Diabetes</span>
                {reviewFlagBadge(result.diabetes_review_flag)}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[14px] text-text-muted">
                  Family history of kidney disease
                </span>
                {reviewFlagBadge(result.family_history_flag)}
              </div>
            </div>
          </Card>

          <p className="text-[12px] text-text-muted">{result.source_citation}</p>
        </>
      )}
    </div>
  )
}

function StatTile({ label, value }) {
  return (
    <div className="border border-border rounded-lg bg-surface p-4">
      <p className="text-[13px] text-text-muted">{label}</p>
      <p className="text-[24px] font-bold text-text tabular-nums">{value}</p>
    </div>
  )
}

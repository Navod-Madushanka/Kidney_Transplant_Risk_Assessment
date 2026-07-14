// src/pages/HlaTypingStep.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { HLA_LOCUS_OPTIONS } from "../constants/clinicalEnums"
import Card from "../components/ui/Card"
import InputField from "../components/ui/InputField"
import Button from "../components/ui/Button"

function validateHlaRows(rows) {
  // Keyed by locus so LocusCard can look up "does *this* locus have an
  // error" without scanning the whole array on every render.
  const errorsByLocus = {}
  for (const row of rows) {
    if (!row.allele_1.trim() || !row.allele_2.trim()) {
      errorsByLocus[row.locus] = "Both alleles are required"
    }
  }
  return errorsByLocus
}

function LocusCard({ locusLabel, locus, patientRow, donorRow, onPatientChange, onDonorChange, patientError, donorError }) {
  return (
    <Card>
      <Card.Header
        title={locusLabel}
        subtitle={locus === "DRB3,4,5" ? "Some people don't express all three — enter what the report shows" : undefined}
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        <div className="flex flex-col gap-3">
          <p className="text-[13px] font-semibold text-text-muted">Patient</p>
          <div className="grid grid-cols-2 gap-3">
            <InputField
              label="Allele 1"
              value={patientRow.allele_1}
              onChange={(e) => onPatientChange({ allele_1: e.target.value })}
              error={patientError}
              required
            />
            <InputField
              label="Allele 2"
              value={patientRow.allele_2}
              onChange={(e) => onPatientChange({ allele_2: e.target.value })}
              required
            />
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <p className="text-[13px] font-semibold text-text-muted">Donor</p>
          <div className="grid grid-cols-2 gap-3">
            <InputField
              label="Allele 1"
              value={donorRow.allele_1}
              onChange={(e) => onDonorChange({ allele_1: e.target.value })}
              error={donorError}
              required
            />
            <InputField
              label="Allele 2"
              value={donorRow.allele_2}
              onChange={(e) => onDonorChange({ allele_2: e.target.value })}
              required
            />
          </div>
        </div>
      </div>
    </Card>
  )
}

export default function HlaTypingStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  const [patientErrors, setPatientErrors] = useState({})
  const [donorErrors, setDonorErrors] = useState({})

  function handleContinue() {
    const nextPatientErrors = validateHlaRows(state.patient_hla)
    const nextDonorErrors = validateHlaRows(state.donor_hla)
    setPatientErrors(nextPatientErrors)
    setDonorErrors(nextDonorErrors)

    const hasErrors =
      Object.keys(nextPatientErrors).length > 0 ||
      Object.keys(nextDonorErrors).length > 0

    if (hasErrors) return

    actions.unlockStep(3)
    navigate("/checks/new/sensitization")
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">HLA typing</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Enter both alleles for every locus, for both patient and donor — this feeds
          directly into the mismatch risk score.
        </p>
      </div>

      {HLA_LOCUS_OPTIONS.map((option) => {
        const patientRow = state.patient_hla.find((row) => row.locus === option.value)
        const donorRow = state.donor_hla.find((row) => row.locus === option.value)

        return (
          <LocusCard
            key={option.value}
            locus={option.value}
            locusLabel={option.label}
            patientRow={patientRow}
            donorRow={donorRow}
            patientError={patientErrors[option.value]}
            donorError={donorErrors[option.value]}
            onPatientChange={(patch) => actions.setPatientHlaRow(option.value, patch)}
            onDonorChange={(patch) => actions.setDonorHlaRow(option.value, patch)}
          />
        )
      })}

      <div className="flex items-center justify-between">
        <Button variant="secondary" onClick={() => navigate("/checks/new/details")}>
          Back
        </Button>
        <Button size="lg" onClick={handleContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}
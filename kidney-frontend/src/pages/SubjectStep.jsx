// src/pages/SubjectStep.jsx
import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { getPatient } from "../api/patients"
import { getDonor } from "../api/donors"
import { getCompatibilityReadiness } from "../api/compatibility"
import { createPair } from "../api/pairs"
import { hasAnyValue } from "../utils/ocrHydrate"
import Card from "../components/ui/Card"
import Button from "../components/ui/Button"
import PatientForm from "../components/domain/patient/PatientForm"
import DonorForm from "../components/domain/donor/DonorForm"

// Patient/donor Full name/DOB/blood group/Rh/NIC read the same way
// regardless of source (OCR off the documents from the now-preceding
// Photos step, or a plain empty form) -- PatientForm/DonorForm's
// initialValues just need the wizard's snake_case detail fields remapped
// to their camelCase form-field names. Sex/weight and the donor's clinical
// panel aren't part of patient_details/donor_details (OCR doesn't read
// those off an HLA typing report), so they're left for the doctor to fill
// in here regardless of what got extracted.
function formValuesFromDetails(details) {
  return {
    fullName: details.full_name || "",
    dateOfBirth: details.date_of_birth || "",
    bloodType: details.blood_type || "",
    rhFactor: details.rh_factor || "",
    nicNumber: details.nic_number || "",
  }
}

// Seeds patient_details/donor_details from the linked record's own
// demographic fields -- without this, DetailsStep would open blank even
// though a real, already-filled-in record was just selected, and Continue
// there would overwrite that record with empty strings. This is a plain
// snapshot copy, not a live binding: DetailsStep (and OCR) can still change
// these fields freely from here on. See wizardReducer.js's subject
// docstring for why the patientRecord/donorRecord snapshot is kept
// separately from this.
function detailsFromRecord(record) {
  return {
    full_name: record.full_name,
    nic_number: record.nic_number || "",
    date_of_birth: record.date_of_birth,
    blood_type: record.blood_type,
    rh_factor: record.rh_factor,
  }
}

function GapList({ title, tone, gaps, linkFor }) {
  if (gaps.length === 0) return null
  const toneClasses =
    tone === "high-risk"
      ? "border-high-risk/30 bg-high-risk-subtle text-high-risk"
      : "border-moderate/30 bg-moderate-subtle text-moderate"

  return (
    <div className={`rounded-md border p-4 ${toneClasses}`}>
      <p className="text-[13px] font-semibold">{title}</p>
      <ul className="mt-2 flex flex-col gap-1.5">
        {gaps.map((gap) => (
          <li key={gap.code} className="text-[13px] flex items-center justify-between gap-3">
            <span className="break-words">{gap.label}</span>
            {linkFor && (
              <Link to={linkFor(gap)} className="underline shrink-0">
                Fix
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function SubjectStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  const [readinessState, setReadinessState] = useState("idle") // idle | loading | loaded | error

  const { patientId, donorId, readiness } = state.subject

  // This step no longer offers a "pick an existing patient/donor from the
  // database" UI -- that only lives on NewCheckFromRecordsPage.jsx now,
  // which forwards here with patientId/donorId already chosen (seeded by
  // WizardProvider's location.state lazy-init). Reaching this step with
  // neither set means a doctor started a plain "New compatibility check",
  // so the only way forward is registering a brand-new patient + donor
  // right here.
  const needsRegistration = !patientId || !donorId

  const [patientPayload, setPatientPayload] = useState(null)
  const [donorPayload, setDonorPayload] = useState(null)
  const [isRegistering, setIsRegistering] = useState(false)
  const [registerError, setRegisterError] = useState("")

  // Sidesteps a real race: dispatching setSubject from handleRegister below
  // re-renders this component with a new patientId/donorId *before* the
  // navigate() call two lines later actually swaps the route out, so this
  // effect's dependency array sees the change and would otherwise fire --
  // redundantly re-fetching readiness/records handleRegister already has,
  // and (worse) briefly repopulating state.subject.readiness with a
  // blocking gap this same effect has no UI left on screen to show.
  const skipNextReadinessFetch = useRef(false)

  useEffect(() => {
    if (!patientId || !donorId) return
    if (skipNextReadinessFetch.current) {
      skipNextReadinessFetch.current = false
      return
    }
    let cancelled = false
    setReadinessState("loading")
    Promise.all([
      getCompatibilityReadiness(patientId, donorId),
      getPatient(patientId),
      getDonor(donorId),
    ])
      .then(([readinessResult, patientRecord, donorRecord]) => {
        if (cancelled) return
        actions.setReadiness(readinessResult)
        actions.setLinkedRecords(patientRecord, donorRecord)
        actions.setPatientDetails(detailsFromRecord(patientRecord))
        actions.setDonorDetails(detailsFromRecord(donorRecord))
        setReadinessState("loaded")
      })
      .catch(() => !cancelled && setReadinessState("error"))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- actions is a stable memo, re-running on it would refetch every render
  }, [patientId, donorId])

  const canContinue = readinessState === "loaded" && readiness?.can_run

  function handleContinue() {
    actions.unlockStep(2)
    navigate("/checks/new/details")
  }

  // One transaction on the backend (POST /pairs) -- a NIC conflict on
  // either side rolls the whole thing back, so there's no orphaned patient
  // to worry about on retry.
  //
  // Deliberately skips the readiness/blocking-gap preview below and goes
  // straight to Details (Confirm details -- next in line now that Photos
  // moved ahead of this step), the same way this wizard worked before Part
  // E introduced that preview for re-used *existing* records (see
  // compatibility_precondition_service.py's module docstring). A pair
  // registered right here is brand new by definition -- it will always be
  // missing HLA typing, since HlaTypingStep (a few steps from now) is where
  // that gets entered. Showing "these must be resolved" for a gap the very
  // next steps exist to fill would just dead-end the doctor.
  async function handleRegister() {
    setRegisterError("")
    setIsRegistering(true)
    try {
      const pair = await createPair({ patient: patientPayload, donor: donorPayload })
      skipNextReadinessFetch.current = true
      actions.setSubject({ patientId: pair.patient_id, donorId: pair.donor_id })
      actions.setLinkedRecords(pair.patient, pair.donor)
      actions.setPatientDetails(detailsFromRecord(pair.patient))
      actions.setDonorDetails(detailsFromRecord(pair.donor))
      actions.unlockStep(2)
      navigate("/checks/new/details")
    } catch (err) {
      setRegisterError(err.message || "Couldn't register this pair. Please try again.")
      setIsRegistering(false)
    }
  }

  if (needsRegistration) {
    const patientHydrated = hasAnyValue(state.patient_details)
    const donorHydrated = hasAnyValue(state.donor_details)

    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-[22px] font-bold text-text">Patient &amp; donor</h1>
          <p className="text-[14px] text-text-muted mt-1">
            Register the patient and donor this check is for. Everything the check writes — HLA
            typing, sensitization events, the check itself — is saved onto these two new records.
          </p>
        </div>

        <div>
          <h2 className="text-[17px] font-semibold text-text mb-1">Patient</h2>
          {patientHydrated && (
            <p className="text-[13px] text-clear font-medium mb-2">
              Auto-filled from the documents you uploaded — review before registering.
            </p>
          )}
          <Card>
            <PatientForm
              key={JSON.stringify(state.patient_details)}
              initialValues={formValuesFromDetails(state.patient_details)}
              submitLabel={patientPayload ? "Patient details saved — update" : "Save patient details"}
              onSubmit={(payload) => {
                setPatientPayload(payload)
                return Promise.resolve()
              }}
            />
          </Card>
        </div>

        <div>
          <h2 className="text-[17px] font-semibold text-text mb-1">Donor</h2>
          {donorHydrated && (
            <p className="text-[13px] text-clear font-medium mb-2">
              Auto-filled from the documents you uploaded — review before registering.
            </p>
          )}
          <Card>
            <DonorForm
              key={JSON.stringify(state.donor_details)}
              initialValues={formValuesFromDetails(state.donor_details)}
              hideIntendedRecipientPicker
              submitLabel={donorPayload ? "Donor details saved — update" : "Save donor details"}
              onSubmit={(payload) => {
                setDonorPayload(payload)
                return Promise.resolve()
              }}
            />
          </Card>
        </div>

        <p className="text-[13px] text-text-muted">
          Already registered this patient or donor?{" "}
          <Link to="/checks/start-from-records" className="text-accent underline">
            Start from their existing records instead
          </Link>
          .
        </p>

        {registerError && (
          <p role="alert" className="text-[13px] text-high-risk font-medium">
            {registerError}
          </p>
        )}

        <div className="flex items-center justify-between">
          <Button variant="secondary" onClick={() => navigate("/checks/new/photos")}>
            Back
          </Button>
          <Button
            size="lg"
            loading={isRegistering}
            disabled={!patientPayload || !donorPayload}
            onClick={handleRegister}
          >
            Register patient &amp; donor
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Patient &amp; donor</h1>
        <p className="text-[14px] text-text-muted mt-1">
          This check runs against the patient and donor below. Everything it writes — HLA typing,
          sensitization events, the check itself — updates these two records.
        </p>
      </div>

      {readinessState === "loading" && (
        <p className="text-[13px] text-text-muted">Checking readiness…</p>
      )}

      {readinessState === "error" && (
        <p className="text-[13px] text-high-risk font-medium">
          Couldn't check readiness for this pair. Please try again.
        </p>
      )}

      {readinessState === "loaded" && state.subject.patientRecord && state.subject.donorRecord && (
        <Card>
          <p className="text-[14px] text-text">
            Patient: <span className="font-semibold">{state.subject.patientRecord.full_name}</span>
            {" · "}
            Donor: <span className="font-semibold">{state.subject.donorRecord.full_name}</span>
          </p>
        </Card>
      )}

      {readinessState === "loaded" && readiness && (
        <>
          <GapList
            title="These must be resolved before the check can run"
            tone="high-risk"
            gaps={readiness.blocking}
            linkFor={(gap) =>
              gap.subject === "patient" ? `/patients/${patientId}` : `/donors/${donorId}`
            }
          />
          <GapList
            title="LKDPI will not be calculated — the check itself will still run normally"
            tone="moderate"
            gaps={readiness.lkdpi_gaps}
            linkFor={(gap) =>
              gap.subject === "patient" ? `/patients/${patientId}` : `/donors/${donorId}`
            }
          />
          <GapList
            title="Donor safety assessment will be incomplete for this donor"
            tone="moderate"
            gaps={[...readiness.donor_risk_projection_gaps, ...readiness.donor_risk_contraindication_gaps]}
            linkFor={() => `/donors/${donorId}`}
          />
          {readiness.can_run &&
            readiness.lkdpi_gaps.length === 0 &&
            readiness.donor_risk_projection_gaps.length === 0 &&
            readiness.donor_risk_contraindication_gaps.length === 0 && (
              <div className="rounded-md border border-clear/30 bg-clear-subtle p-4">
                <p className="text-[13px] font-semibold text-clear">
                  Ready to check — nothing is missing on either record.
                </p>
              </div>
            )}
        </>
      )}

      <div className="flex items-center justify-between">
        <Button variant="secondary" onClick={() => navigate("/checks/new/photos")}>
          Back
        </Button>
        <Button size="lg" onClick={handleContinue} disabled={!canContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}

// src/pages/SubjectStep.jsx
import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import { listPatients, getPatient } from "../api/patients"
import { listDonors, getDonor } from "../api/donors"
import { getCompatibilityReadiness } from "../api/compatibility"
import Card from "../components/ui/Card"
import Select from "../components/ui/Select"
import Button from "../components/ui/Button"

function personLabel(person) {
  return `${person.full_name} — ${person.nic_number || "no NIC"}`
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

  const [patients, setPatients] = useState([])
  const [donors, setDonors] = useState([])
  const [loadState, setLoadState] = useState("loading")
  const [readinessState, setReadinessState] = useState("idle") // idle | loading | loaded | error

  const { patientId, donorId, readiness } = state.subject

  useEffect(() => {
    let cancelled = false
    Promise.all([listPatients(), listDonors()])
      .then(([patientList, donorList]) => {
        if (cancelled) return
        setPatients(patientList)
        setDonors(donorList)
        setLoadState("loaded")
      })
      .catch(() => !cancelled && setLoadState("error"))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!patientId || !donorId) return
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
    actions.unlockStep(1)
    navigate("/checks/new/photos")
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Patient &amp; donor</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Pick the two existing records this check runs against. Everything the check writes —
          HLA typing, sensitization events, the check itself — updates these records rather than
          creating new ones, so re-checking the same real pair later works cleanly.
        </p>
      </div>

      <Card>
        {loadState === "error" ? (
          <p className="text-[14px] text-text-muted">
            Couldn't load patients and donors. Please refresh the page.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Select
              label="Patient"
              placeholder={loadState === "loading" ? "Loading…" : "Select patient"}
              disabled={loadState === "loading"}
              options={patients.map((p) => ({ value: p.id, label: personLabel(p) }))}
              value={patientId || ""}
              onChange={(e) => actions.setSubject({ patientId: e.target.value })}
            />
            <Select
              label="Donor"
              placeholder={loadState === "loading" ? "Loading…" : "Select donor"}
              disabled={loadState === "loading"}
              options={donors.map((d) => ({ value: d.id, label: personLabel(d) }))}
              value={donorId || ""}
              onChange={(e) => actions.setSubject({ donorId: e.target.value })}
            />
          </div>
        )}
        <p className="text-[13px] text-text-muted mt-4">
          Don't see the person you need?{" "}
          <Link to="/patients/new" className="text-accent underline">
            Register a new patient
          </Link>{" "}
          or{" "}
          <Link to="/donors/new" className="text-accent underline">
            register a new donor
          </Link>
          , then come back and select them here.
        </p>
      </Card>

      {patientId && donorId && readinessState === "loading" && (
        <p className="text-[13px] text-text-muted">Checking readiness…</p>
      )}

      {readinessState === "error" && (
        <p className="text-[13px] text-high-risk font-medium">
          Couldn't check readiness for this pair. Please try again.
        </p>
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

      <div className="flex justify-end">
        <Button size="lg" onClick={handleContinue} disabled={!canContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}

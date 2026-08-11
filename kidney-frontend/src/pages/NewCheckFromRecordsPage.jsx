// src/pages/NewCheckFromRecordsPage.jsx
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { listPatients } from "../api/patients"
import { listDonors } from "../api/donors"
import {
  listPatientReportFiles,
  listPairReportFiles,
  fetchPatientReportFileBlob,
  fetchPairReportFileBlob,
} from "../api/reportFiles"
import { listPairs } from "../api/pairs"
import { PREFILL_SLOTS, resolvePrefillPhotos } from "../utils/resolvePrefillPhotos"
import Card from "../components/ui/Card"
import Select from "../components/ui/Select"
import Button from "../components/ui/Button"

const SOURCE_LABELS = { patient: "patient's records", pair: "this pair's records" }

function personLabel(person) {
  return `${person.full_name} — ${person.nic_number || "no NIC"}`
}

/**
 * Lets a doctor pick an existing patient + donor and start a compatibility
 * check with the Photos step pre-filled from whatever those two records
 * already have archived in their Report files card (see ReportFilesCard.jsx)
 * — a doctor doesn't have to re-locate and re-upload a document that's
 * already on file. Both IDs are carried into the wizard alongside the
 * prefilled photos (see WizardProvider's lazy-init) so SubjectStep opens
 * with this exact pair pre-selected instead of asking the doctor to pick
 * it again.
 */
export default function NewCheckFromRecordsPage() {
  const navigate = useNavigate()

  const [patients, setPatients] = useState([])
  const [donors, setDonors] = useState([])
  const [loadState, setLoadState] = useState("loading")

  const [patientId, setPatientId] = useState("")
  const [donorId, setDonorId] = useState("")

  const [matches, setMatches] = useState(null) // resolvePrefillPhotos() result, once both are picked
  const [pairId, setPairId] = useState(null) // the DonorPatientPair linking this patient+donor, if any
  const [isResolving, setIsResolving] = useState(false)
  const [resolveError, setResolveError] = useState("")

  const [isStarting, setIsStarting] = useState(false)
  const [startError, setStartError] = useState("")

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
    if (!patientId || !donorId) {
      setMatches(null)
      setPairId(null)
      return
    }
    let cancelled = false
    setIsResolving(true)
    setResolveError("")
    Promise.all([listPatientReportFiles(patientId), listPairs({ patientId, donorId })])
      .then(async ([patientFiles, pairs]) => {
        if (cancelled) return
        const pair = pairs[0] ?? null
        setPairId(pair?.id ?? null)
        const pairFiles = pair ? await listPairReportFiles(pair.id) : []
        if (cancelled) return
        setMatches(resolvePrefillPhotos(pairFiles, patientFiles))
      })
      .catch(() => {
        if (cancelled) return
        setResolveError("Couldn't check archived report files for this pair. You can still start the check and upload documents manually.")
        setMatches(null)
        setPairId(null)
      })
      .finally(() => !cancelled && setIsResolving(false))
    return () => {
      cancelled = true
    }
  }, [patientId, donorId])

  const foundCount = matches ? Object.values(matches).filter(Boolean).length : 0

  async function handleStart() {
    setStartError("")
    setIsStarting(true)
    try {
      const prefillPhotos = {}
      if (matches) {
        for (const { slot } of PREFILL_SLOTS) {
          const match = matches[slot]
          if (!match) continue
          const blob =
            match.source === "patient"
              ? await fetchPatientReportFileBlob(patientId, match.reportFile.id)
              : await fetchPairReportFileBlob(pairId, match.reportFile.id)
          prefillPhotos[slot] = new File([blob], match.reportFile.original_filename, {
            type: match.reportFile.content_type,
          })
        }
      }
      navigate("/checks/new/subject", { state: { prefillPhotos, patientId, donorId } })
    } catch (err) {
      setStartError(err.message || "Couldn't load the archived documents. Please try again.")
      setIsStarting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <h1 className="text-[22px] font-bold text-text">Start check from existing records</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Pick a patient and a donor who already have report files on file — their archived
          documents will pre-fill the compatibility check's Photos step. Nothing else about the
          check changes, and you can still review, replace, or add documents there before
          extracting.
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
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
            />
            <Select
              label="Donor"
              placeholder={loadState === "loading" ? "Loading…" : "Select donor"}
              disabled={loadState === "loading"}
              options={donors.map((d) => ({ value: d.id, label: personLabel(d) }))}
              value={donorId}
              onChange={(e) => setDonorId(e.target.value)}
            />
          </div>
        )}
      </Card>

      {patientId && donorId && (
        <Card>
          <Card.Header
            title="Archived documents found"
            subtitle={
              isResolving
                ? "Checking…"
                : matches
                  ? `${foundCount} of ${PREFILL_SLOTS.length} photo slots will be pre-filled`
                  : undefined
            }
          />
          {resolveError && <p className="text-[13px] text-high-risk font-medium">{resolveError}</p>}
          {!isResolving && matches && (
            <ul className="flex flex-col divide-y divide-border">
              {PREFILL_SLOTS.map(({ slot, label }) => {
                const match = matches[slot]
                return (
                  <li key={slot} className="py-2.5 flex items-center justify-between gap-3 text-[14px]">
                    <span className="text-text">{label}</span>
                    {match ? (
                      <span className="text-[13px] text-clear font-medium">
                        Found in {SOURCE_LABELS[match.source]} — {match.reportFile.original_filename}
                      </span>
                    ) : (
                      <span className="text-[13px] text-text-muted">Not archived — upload manually</span>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      )}

      {startError && <p className="text-[13px] text-high-risk font-medium">{startError}</p>}

      <div className="flex justify-end">
        <Button
          size="lg"
          disabled={!patientId || !donorId || isResolving}
          loading={isStarting}
          onClick={handleStart}
        >
          Start compatibility check
        </Button>
      </div>
    </div>
  )
}

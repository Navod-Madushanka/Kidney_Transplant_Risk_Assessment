// src/components/domain/reportFiles/PairDocumentsCard.jsx
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Card from "../../ui/Card"
import Button from "../../ui/Button"
import { listPairs } from "../../../api/pairs"
import { listPairReportFiles, downloadPairReportFile } from "../../../api/reportFiles"
import { getPatient } from "../../../api/patients"
import { getDonor } from "../../../api/donors"
import { PAIR_REPORT_CATEGORY_OPTIONS } from "../../../constants/reportFileCategory"

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Read-only view of a DonorPatientPair's joint documents (HLA typing,
 * crossmatch report) -- no upload/delete/replace here, since donors own no
 * documents and a patient's joint documents can only be attached through
 * pair registration (see NewPairPage.jsx). Pass exactly one of
 * patientId/donorId; the other person's name is looked up and shown as the
 * "linked" line.
 */
export default function PairDocumentsCard({ patientId, donorId }) {
  const [loadState, setLoadState] = useState("loading")
  const [pair, setPair] = useState(null)
  const [files, setFiles] = useState([])
  const [linkedPerson, setLinkedPerson] = useState(null)

  // Falls back to "loading" (rather than flashing the previous pair's
  // documents) the moment patientId/donorId changes, via a render-time
  // state adjustment instead of a setState call in the effect body.
  const [syncedKey, setSyncedKey] = useState(`${patientId ?? ""}:${donorId ?? ""}`)
  const currentKey = `${patientId ?? ""}:${donorId ?? ""}`
  if (currentKey !== syncedKey) {
    setSyncedKey(currentKey)
    setLoadState("loading")
  }

  useEffect(() => {
    let cancelled = false

    listPairs({ patientId, donorId })
      .then(async (pairs) => {
        if (cancelled) return
        const found = pairs[0] ?? null
        setPair(found)
        if (!found) {
          setFiles([])
          setLinkedPerson(null)
          setLoadState("loaded")
          return
        }

        const [pairFiles, person] = await Promise.all([
          listPairReportFiles(found.id),
          patientId ? getDonor(found.donor_id) : getPatient(found.patient_id),
        ])
        if (cancelled) return
        setFiles(pairFiles)
        setLinkedPerson(person)
        setLoadState("loaded")
      })
      .catch(() => !cancelled && setLoadState("error"))

    return () => {
      cancelled = true
    }
  }, [patientId, donorId])

  return (
    <Card>
      <Card.Header
        title="Pair documents"
        subtitle="HLA typing and crossmatch reports cover the whole pair, so they're archived on the pair, not either person — for reference only."
      />

      {loadState === "loading" ? (
        <div className="flex justify-center py-6">
          <div
            className="h-6 w-6 rounded-full border-2 border-border border-t-accent animate-spin"
            role="status"
            aria-label="Loading"
          />
        </div>
      ) : loadState === "error" ? (
        <p className="text-[14px] text-text-muted">Couldn't load pair documents. Please refresh the page.</p>
      ) : !pair ? (
        <p className="text-[14px] text-text-muted">
          Not registered as a pair yet — joint documents can only be attached through{" "}
          <Link to="/pairs/new" className="text-accent font-medium">
            pair registration
          </Link>
          .
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-[13px] text-text-muted">
            {patientId ? "Linked donor" : "Linked patient"}:{" "}
            <span className="text-text font-medium">{linkedPerson?.full_name ?? "Loading…"}</span>
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {PAIR_REPORT_CATEGORY_OPTIONS.map(({ value, label }) => {
              const file = files.find((f) => f.category === value)
              return (
                <div key={value} className="rounded-lg border border-border p-3 flex flex-col gap-2">
                  <p className="text-[13px] font-semibold text-text">{label}</p>
                  {file ? (
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[14px] text-text font-medium truncate">
                          {file.original_filename}
                        </p>
                        <p className="text-[13px] text-text-muted">{formatFileSize(file.size_bytes)}</p>
                      </div>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => downloadPairReportFile(pair.id, file.id, file.original_filename)}
                      >
                        Download
                      </Button>
                    </div>
                  ) : (
                    <p className="text-[13px] text-text-muted">Not archived</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </Card>
  )
}

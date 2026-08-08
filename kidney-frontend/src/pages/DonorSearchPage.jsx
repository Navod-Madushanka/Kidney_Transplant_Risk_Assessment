// src/pages/DonorSearchPage.jsx
import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getPatient } from "../api/patients"
import { searchCompatibleDonors } from "../api/donorSearch"
import { runCompatibilityCheck } from "../api/compatibility"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import Table from "../components/ui/Table"

export default function DonorSearchPage() {
  const { patientId } = useParams()
  const navigate = useNavigate()

  const [patient, setPatient] = useState(null)
  const [state, setState] = useState({ status: "loading", candidates: [] })
  const [pursuingDonorId, setPursuingDonorId] = useState(null)
  const [pursueError, setPursueError] = useState(null)

  useEffect(() => {
    let cancelled = false

    getPatient(patientId).then((data) => !cancelled && setPatient(data))

    searchCompatibleDonors(patientId)
      .then((candidates) => !cancelled && setState({ status: "loaded", candidates }))
      .catch(() => !cancelled && setState({ status: "error", candidates: [] }))

    return () => {
      cancelled = true
    }
  }, [patientId])

  async function handlePursue(donorId) {
    setPursueError(null)
    setPursuingDonorId(donorId)
    try {
      const report = await runCompatibilityCheck(patientId, donorId)
      navigate(`/reports/${report.id}`)
    } catch {
      // Most likely cause: the donor was reserved/transplanted by its
      // owning doctor between search and this click — get_donor_for_
      // compatibility_check re-checks status fresh, so this cleanly 404s
      // rather than silently succeeding.
      setPursueError(
        "Couldn't start a compatibility check with that donor — they may no longer be available. Try refreshing the search."
      )
      setPursuingDonorId(null)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      <div>
        <h1 className="text-[22px] font-bold text-text">Search compatible donors</h1>
        <p className="text-[14px] text-text-muted">
          {patient
            ? `System-wide available donors compatible with ${patient.full_name}.`
            : "Loading patient…"}
        </p>
      </div>

      {pursueError && (
        <div className="border border-high-risk rounded-lg p-4 bg-high-risk-subtle">
          <p className="text-[14px] text-high-risk">{pursueError}</p>
        </div>
      )}

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
            Couldn't load candidate donors. Please try refreshing.
          </p>
        </div>
      )}

      {state.status === "loaded" && state.candidates.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center bg-surface">
          <p className="text-[15px] text-text-muted">
            No compatible donors found in the wider pool right now.
          </p>
        </div>
      )}

      {state.status === "loaded" && state.candidates.length > 0 && (
        <Table
          columns={[
            { key: "hospital", label: "Hospital" },
            { key: "doctor", label: "Doctor" },
            { key: "blood_type", label: "Blood type" },
            {
              key: "rh_factor",
              label: (
                <span className="flex flex-col gap-0.5 font-semibold">
                  <span>Rh factor</span>
                  <span className="font-normal normal-case text-[11px] text-text-muted">
                    reference only — not matched
                  </span>
                </span>
              ),
            },
            { key: "mismatches", label: "HLA mismatches" },
            { key: "action", label: "", align: "right" },
          ]}
          rows={state.candidates}
          getRowId={(candidate) => candidate.donor_id}
          renderCell={(candidate, col) => {
            switch (col.key) {
              case "hospital":
                return candidate.hospital_name
              case "doctor":
                return (
                  <div>
                    <p className="text-text font-medium">{candidate.doctor_full_name}</p>
                    <p className="text-[13px] text-text-muted">{candidate.doctor_email}</p>
                  </div>
                )
              case "blood_type":
                return <Badge status="neutral">{candidate.blood_type}</Badge>
              case "rh_factor":
                return (
                  <span
                    className="text-text-muted"
                    title="Rh factor is not a kidney transplant compatibility criterion (unlike blood transfusion) — shown for reference only."
                  >
                    {candidate.rh_factor}
                  </span>
                )
              case "mismatches":
                return candidate.mismatch_result.data_completeness === false
                  ? `${candidate.mismatch_result.total_mismatches} (${candidate.mismatch_result.bucket_name}) — incomplete typing`
                  : `${candidate.mismatch_result.total_mismatches} (${candidate.mismatch_result.bucket_name})`
              case "action":
                return (
                  <Button
                    size="sm"
                    loading={pursuingDonorId === candidate.donor_id}
                    disabled={pursuingDonorId !== null && pursuingDonorId !== candidate.donor_id}
                    onClick={() => handlePursue(candidate.donor_id)}
                  >
                    Run compatibility check
                  </Button>
                )
              default:
                return null
            }
          }}
        />
      )}
    </div>
  )
}

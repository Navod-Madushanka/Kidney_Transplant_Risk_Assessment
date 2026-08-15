// src/pages/BeadSpecificityStep.jsx
import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import InputField from "../components/ui/InputField"
import Button from "../components/ui/Button"
import Card from "../components/ui/Card"
import ToggleSwitch from "../components/ui/ToggleSwitch"

let nextRowId = 1
function makeRow(entry) {
  // Part I (I8): a null MFI means the model flagged this row as illegible,
  // not that a doctor just hasn't typed anything into a blank row yet --
  // those are two different situations that need two different signals.
  // unreadableMfi marks only the former, so the doctor is told to *resolve*
  // (fill in or delete) an AI-flagged gap rather than just fill in a blank.
  const unreadableMfi = entry != null && !!entry.antigen && (entry.mfi === null || entry.mfi === undefined)
  return {
    rowId: nextRowId++,
    antigen: entry?.antigen ?? "",
    mfi: entry?.mfi !== undefined && entry?.mfi !== null ? String(entry.mfi) : "",
    unreadableMfi,
    // Every candidate MFI reconciliation saw when tiles disagreed on this
    // bead (see ocr-service's bead_reconciliation.ReconciledRow.conflict) --
    // `mfi` above is already the highest candidate; this is only for
    // showing the doctor what else was seen.
    conflict: entry?.conflict ?? null,
  }
}

function rowsFromWizardState(beadSpecificity) {
  const rows = beadSpecificity.map(makeRow)
  // Always end on one blank row ready for the next entry — matches what a
  // doctor sees on first arriving at this step, and what re-arriving after
  // navigating back should also look like.
  rows.push(makeRow())
  return rows
}

export default function BeadSpecificityStep() {
  const navigate = useNavigate()
  const { state, actions } = useWizard()

  const [rows, setRows] = useState(() => rowsFromWizardState(state.bead_specificity))
  const [rowErrors, setRowErrors] = useState({})

  // Bead charts routinely run to 50+ rows — these narrow what's rendered
  // so a doctor reviewing/verifying OCR-extracted values isn't stuck
  // scrolling through all of them to find one antigen or reach Continue.
  // Separate fields (not a combined search) since MFI values are numeric
  // and antigen names aren't, and a doctor typically knows which one
  // they're looking up by.
  const [antigenFilter, setAntigenFilter] = useState("")
  const [mfiFilter, setMfiFilter] = useState("")
  const hasActiveFilter = antigenFilter.trim() !== "" || mfiFilter.trim() !== ""
  const [verificationError, setVerificationError] = useState(false)

  // Either page counts as "OCR extracted this document" — they merge into
  // one bead_specificity array, so one confirmation covers both. See
  // ocr_verified's comment in wizardReducer.js. Also true when the
  // patient's antibody profile is already flagged unverified in their
  // record (antibody_profile_verified === false) -- e.g. the registration-
  // time background extraction job (see NewPairPage.jsx) saved it
  // unattended, or the "start from records" prefill pulled in data nobody's
  // reviewed yet. patientRecord is fetched fresh from GET /patients/{id}
  // on every wizard entry path (see SubjectStep.jsx), so this catches "not
  // yet confirmed" regardless of whether THIS session is what extracted it.
  const wasOcrExtracted =
    state.extraction?.documents?.["bead_specificity_page_1"]?.status === "done" ||
    state.extraction?.documents?.["bead_specificity_page_2"]?.status === "done" ||
    state.subject?.patientRecord?.antibody_profile_verified === false

  // Part I (I8): the doctor must supply or delete each AI-flagged
  // unreadable value rather than being able to confirm a chart with holes
  // in it -- gates the verification toggle below, separately from (and in
  // addition to) the per-row "MFI is required" validation Continue already
  // enforces.
  const hasUnresolvedUnreadableRows = rows.some((row) => row.unreadableMfi)

  const visibleRows = useMemo(() => {
    if (!hasActiveFilter) return rows
    const antigenTerm = antigenFilter.trim().toLowerCase()
    const mfiTerm = mfiFilter.trim().toLowerCase()
    return rows.filter((row) => {
      const matchesAntigen = !antigenTerm || row.antigen.toLowerCase().includes(antigenTerm)
      const matchesMfi = !mfiTerm || row.mfi.toLowerCase().includes(mfiTerm)
      return matchesAntigen && matchesMfi
    })
  }, [rows, antigenFilter, mfiFilter, hasActiveFilter])

  function updateRow(rowId, field, value) {
    setRows((prev) => {
      const index = prev.findIndex((row) => row.rowId === rowId)
      if (index === -1) return prev

      const updated = { ...prev[index], [field]: value }
      // The doctor typed a real value into a row the AI couldn't read --
      // resolved, whatever they entered is now the value of record.
      if (field === "mfi" && value.trim()) {
        updated.unreadableMfi = false
      }
      const isLastRow = index === prev.length - 1
      const next = [...prev]
      next[index] = updated

      // Auto-expand: the last row just got its antigen filled in for the
      // first time — append a fresh blank row after it. Only antigen
      // triggers this (see rationale above); typing into mfi never does.
      if (isLastRow && field === "antigen" && value.trim() && !prev[index].antigen.trim()) {
        next.push(makeRow())
      }

      return next
    })
  }

  function removeRow(rowId) {
    setRows((prev) => {
      const filtered = prev.filter((row) => row.rowId !== rowId)
      // Never let the list end with zero rows — always leave one blank
      // entry point available.
      const hasTrailingBlank =
        filtered.length > 0 && !filtered[filtered.length - 1].antigen.trim()
      return hasTrailingBlank || filtered.length === 0
        ? filtered.length === 0
          ? [makeRow()]
          : filtered
        : [...filtered, makeRow()]
    })
  }

  function handleContinue() {
    const nextRowErrors = {}
    const populatedRows = []

    rows.forEach((row, index) => {
      const isLastRow = index === rows.length - 1
      const hasAntigen = row.antigen.trim().length > 0
      const hasMfi = row.mfi.trim().length > 0

      if (!hasAntigen && !hasMfi) {
        // A genuinely empty row is only fine as the trailing placeholder.
        if (!isLastRow) {
          nextRowErrors[row.rowId] = "Remove this row or fill it in"
        }
        return
      }

      if (!hasAntigen) {
        nextRowErrors[row.rowId] = "Antigen is required"
        return
      }
      if (hasMfi && Number.isNaN(Number(row.mfi))) {
        nextRowErrors[row.rowId] = "MFI must be a number"
        return
      }
      if (!hasMfi) {
        nextRowErrors[row.rowId] = "MFI is required"
        return
      }

      populatedRows.push({ antigen: row.antigen.trim(), mfi: Number(row.mfi) })
    })

    setRowErrors(nextRowErrors)
    const needsVerification =
      (wasOcrExtracted && !state.ocr_verified?.bead_specificity) || hasUnresolvedUnreadableRows
    setVerificationError(needsVerification)

    if (Object.keys(nextRowErrors).length > 0) {
      // A row failing validation could be hidden behind an active search —
      // clear it so the doctor can actually see what needs fixing.
      setAntigenFilter("")
      setMfiFilter("")
      return
    }
    if (needsVerification) return

    actions.setBeadSpecificity(populatedRows)
    actions.unlockStep(6)
    navigate("/checks/new/review")
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-bold text-text">Bead specificity report</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Transcribe each antigen and its MFI value from the bead chart — a new row
          appears automatically as you go.
        </p>
      </div>

      <Card>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <InputField
            label="Search by antigen/bead name"
            placeholder="e.g. B*44:02"
            value={antigenFilter}
            onChange={(e) => setAntigenFilter(e.target.value)}
          />
          <InputField
            label="Search by MFI value"
            placeholder="e.g. 3500"
            inputMode="decimal"
            value={mfiFilter}
            onChange={(e) => setMfiFilter(e.target.value)}
          />
        </div>

        {hasActiveFilter && (
          <p className="text-[13px] text-text-muted mt-3">
            Showing {visibleRows.length} of {rows.length} rows
          </p>
        )}
      </Card>

      <Card>
        {/* Bead charts routinely run to 50+ rows — scrolling this list
            internally (rather than the whole page) keeps Back/Continue
            reachable without hunting for them below a long list. */}
        <div className="flex flex-col gap-3 max-h-105 overflow-y-auto pr-1">
          {visibleRows.length === 0 ? (
            <p className="text-[14px] text-text-muted text-center py-4">
              No rows match your search.
            </p>
          ) : (
            visibleRows.map((row) => (
              <div key={row.rowId} className="flex flex-col gap-1">
                <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
                  <InputField
                    placeholder="Antigen (e.g. B*44:02)"
                    value={row.antigen}
                    onChange={(e) => updateRow(row.rowId, "antigen", e.target.value)}
                    error={rowErrors[row.rowId]}
                  />
                  <InputField
                    placeholder={row.unreadableMfi ? "Couldn't read this value" : "MFI value"}
                    inputMode="decimal"
                    value={row.mfi}
                    onChange={(e) => updateRow(row.rowId, "mfi", e.target.value)}
                    error={
                      row.unreadableMfi
                        ? "AI couldn't read this value — enter it manually or remove the row"
                        : undefined
                    }
                  />
                  <button
                    type="button"
                    onClick={() => removeRow(row.rowId)}
                    aria-label="Remove row"
                    className="h-11 w-11 flex items-center justify-center text-text-muted hover:text-high-risk"
                  >
                    ✕
                  </button>
                </div>
                {row.conflict && (
                  <p className="text-[12px] text-moderate pl-1">
                    Tiles disagreed on this value ({row.conflict.map((c) => (c === null ? "unreadable" : c)).join(", ")}) —
                    using the highest reading; verify against the source chart.
                  </p>
                )}
              </div>
            ))
          )}
        </div>
      </Card>

      {wasOcrExtracted && (
        <div
          className={[
            "rounded-md border p-4",
            verificationError ? "border-high-risk bg-high-risk-subtle" : "border-moderate bg-moderate-subtle",
          ].join(" ")}
        >
          <ToggleSwitch
            label="I have reviewed this bead specificity chart against the source document"
            helperText={
              hasUnresolvedUnreadableRows
                ? "Resolve every unreadable MFI value below (enter it manually or remove the row) before confirming."
                : "MFI values here were extracted by AI — confirm they're accurate before continuing. A misread value can flow straight into a DSA reject."
            }
            checked={!!state.ocr_verified?.bead_specificity}
            disabled={hasUnresolvedUnreadableRows}
            onChange={(checked) => {
              actions.setOcrVerified("bead_specificity", checked)
              if (checked) setVerificationError(false)
            }}
          />
          {verificationError && (
            <p className="text-[13px] text-high-risk font-medium mt-2">
              {hasUnresolvedUnreadableRows
                ? "Resolve every unreadable MFI value above before continuing."
                : "Confirm this before continuing — the compatibility check refuses to run on unverified OCR data."}
            </p>
          )}
        </div>
      )}

      <div className="flex items-center justify-between">
        <Button variant="secondary" onClick={() => navigate("/checks/new/sensitization")}>
          Back
        </Button>
        <Button size="lg" onClick={handleContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}

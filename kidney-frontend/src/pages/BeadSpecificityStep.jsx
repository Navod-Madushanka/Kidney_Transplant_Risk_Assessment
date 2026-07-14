// src/pages/BeadSpecificityStep.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useWizard } from "../hooks/useWizard"
import InputField from "../components/ui/InputField"
import Button from "../components/ui/Button"
import Card from "../components/ui/Card"

let nextRowId = 1
function makeRow(entry) {
  return {
    rowId: nextRowId++,
    antigen: entry?.antigen ?? "",
    mfi: entry?.mfi !== undefined ? String(entry.mfi) : "",
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

  function updateRow(rowId, field, value) {
    setRows((prev) => {
      const index = prev.findIndex((row) => row.rowId === rowId)
      if (index === -1) return prev

      const updated = { ...prev[index], [field]: value }
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
    if (Object.keys(nextRowErrors).length > 0) return

    actions.setBeadSpecificity(populatedRows)
    actions.unlockStep(5)
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
        <div className="flex flex-col gap-3">
          {rows.map((row) => (
            <div key={row.rowId} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
              <InputField
                placeholder="Antigen (e.g. B*44:02)"
                value={row.antigen}
                onChange={(e) => updateRow(row.rowId, "antigen", e.target.value)}
                error={rowErrors[row.rowId]}
              />
              <InputField
                placeholder="MFI value"
                inputMode="decimal"
                value={row.mfi}
                onChange={(e) => updateRow(row.rowId, "mfi", e.target.value)}
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
          ))}
        </div>
      </Card>

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
// src/components/domain/antibody/AntibodyProfileEditor.jsx
import { useState } from "react"
import InputField from "../../ui/InputField"
import Button from "../../ui/Button"
import Card from "../../ui/Card"
import { isAlleleLevelAntigen, ALLELE_LEVEL_ANTIGEN_ERROR } from "../../../utils/antigenFormat"

let nextRowId = 1
function makeRow(entry) {
  return { rowId: nextRowId++, antigen: entry?.antigen ?? "", mfi: entry?.mfi?.toString() ?? "" }
}

/**
 * Same load-state contract as HlaTypingEditor: "loading" | "loaded" | "error".
 *
 * Usage:
 *   <AntibodyProfileEditor
 *     loadState={loadState}
 *     initialEntries={entries}
 *     onSave={(entries) => replacePatientAntibodyProfiles(patient.id, entries)}
 *   />
 */
export default function AntibodyProfileEditor({ loadState, initialEntries = [], onSave }) {
  const [rows, setRows] = useState(() =>
    initialEntries.length > 0 ? initialEntries.map(makeRow) : [makeRow()]
  )

  // See HlaTypingEditor's matching check -- initialEntries arrives after
  // this component has already mounted (while the parent is still
  // "loading"), so the useState initializer above misses it. Re-sync once
  // real data lands, using React's render-time state-adjustment pattern
  // (comparing against the last-seen value and calling setState during
  // render) instead of an effect, since that runs once before the browser
  // paints rather than causing a second commit. initialEntries' reference
  // stays stable across unrelated re-renders so this won't stomp on
  // in-progress edits.
  const [syncedEntries, setSyncedEntries] = useState(initialEntries)
  if (loadState === "loaded" && initialEntries !== syncedEntries) {
    setSyncedEntries(initialEntries)
    setRows(initialEntries.length > 0 ? initialEntries.map(makeRow) : [makeRow()])
  }

  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState("")
  const [savedAt, setSavedAt] = useState(null)
  const [rowErrors, setRowErrors] = useState({})

  function updateRow(rowId, field, value) {
    setRows((prev) => prev.map((row) => (row.rowId === rowId ? { ...row, [field]: value } : row)))
  }

  function addRow() {
    setRows((prev) => [...prev, makeRow()])
  }

  function removeRow(rowId) {
    setRows((prev) => prev.filter((row) => row.rowId !== rowId))
  }

  async function handleSave() {
    setSaveError("")
    setSavedAt(null)

    const populated = rows.filter((row) => row.antigen.trim() || row.mfi.trim())
    const nextRowErrors = {}
    for (const row of populated) {
      if (!row.antigen.trim()) nextRowErrors[row.rowId] = "Antigen is required"
      else if (isAlleleLevelAntigen(row.antigen.trim())) {
        nextRowErrors[row.rowId] = ALLELE_LEVEL_ANTIGEN_ERROR
      } else if (row.mfi.trim() === "" || Number.isNaN(Number(row.mfi))) {
        nextRowErrors[row.rowId] = "MFI must be a number"
      }
    }
    setRowErrors(nextRowErrors)
    if (Object.keys(nextRowErrors).length > 0) return

    const entries = populated.map((row) => ({ antigen: row.antigen.trim(), mfi: Number(row.mfi) }))

    setIsSaving(true)
    try {
      await onSave(entries)
      setSavedAt(Date.now())
    } catch (err) {
      setSaveError(err.message || "Couldn't save antibody profile. Please try again.")
    } finally {
      setIsSaving(false)
    }
  }

  if (loadState === "loading") {
    return (
      <Card>
        <Card.Header title="Antibody profile (bead chart)" />
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 rounded-full border-2 border-border border-t-accent animate-spin" role="status" aria-label="Loading" />
        </div>
      </Card>
    )
  }

  if (loadState === "error") {
    return (
      <Card>
        <Card.Header title="Antibody profile (bead chart)" />
        <p className="text-[14px] text-text-muted">Couldn't load antibody profile. Please refresh the page.</p>
      </Card>
    )
  }

  return (
    <Card>
      <Card.Header
        title="Antibody profile (bead chart)"
        subtitle="Manually entered or reviewed from an OCR upload — MFI values feed the DSA check"
      />

      <div className="flex flex-col gap-3">
        {rows.map((row) => (
          <div key={row.rowId} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
            <InputField
              placeholder="Antigen (e.g. DQ7)"
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
              aria-label="Remove antibody row"
              className="h-11 w-11 flex items-center justify-center text-text-muted hover:text-high-risk"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 mt-4">
        <Button type="button" variant="secondary" size="sm" onClick={addRow}>
          Add row
        </Button>
        <Button type="button" size="sm" loading={isSaving} onClick={handleSave}>
          Save antibody profile
        </Button>
        {savedAt && !saveError && <span className="text-[13px] text-clear font-medium">Saved</span>}
      </div>

      {saveError && <p className="text-[13px] text-high-risk font-medium mt-2">{saveError}</p>}
    </Card>
  )
}
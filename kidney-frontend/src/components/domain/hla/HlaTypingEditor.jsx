// src/components/domain/hla/HlaTypingEditor.jsx
import { useState } from "react"
import Select from "../../ui/Select"
import InputField from "../../ui/InputField"
import Button from "../../ui/Button"
import Card from "../../ui/Card"
import { HLA_LOCUS_OPTIONS } from "../../../constants/clinicalEnums"

let nextRowId = 1
function makeRow(entry) {
  return {
    rowId: nextRowId++,
    locus: entry?.locus ?? "",
    allele1: entry?.allele_1 ?? "",
    allele2: entry?.allele_2 ?? "",
  }
}

/**
 * loadState: "loading" | "loaded" | "error"
 *
 * Usage:
 *   <HlaTypingEditor
 *     loadState={loadState}
 *     initialEntries={entries}
 *     onSave={(entries) => replacePatientHlaTypings(patient.id, entries)}
 *   />
 */
export default function HlaTypingEditor({ loadState, initialEntries = [], onSave }) {
  const [rows, setRows] = useState(() =>
    initialEntries.length > 0 ? initialEntries.map(makeRow) : [makeRow()]
  )
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState("")
  const [savedAt, setSavedAt] = useState(null)

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
    const entries = rows
      .filter((row) => row.locus && row.allele1 && row.allele2)
      .map((row) => ({ locus: row.locus, allele_1: row.allele1, allele_2: row.allele2 }))

    setIsSaving(true)
    try {
      await onSave(entries)
      setSavedAt(Date.now())
    } catch (err) {
      setSaveError(err.message || "Couldn't save HLA typing. Please try again.")
    } finally {
      setIsSaving(false)
    }
  }

  if (loadState === "loading") {
    return (
      <Card>
        <Card.Header title="HLA typing" />
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 rounded-full border-2 border-border border-t-accent animate-spin" role="status" aria-label="Loading" />
        </div>
      </Card>
    )
  }

  if (loadState === "error") {
    return (
      <Card>
        <Card.Header title="HLA typing" />
        <p className="text-[14px] text-text-muted">Couldn't load HLA typing. Please refresh the page.</p>
      </Card>
    )
  }

  return (
    <Card>
      <Card.Header title="HLA typing" subtitle="Both alleles per locus — this feeds directly into the risk score" />

      <div className="flex flex-col gap-3">
        {rows.map((row) => (
          <div key={row.rowId} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 items-start">
            <Select
              options={HLA_LOCUS_OPTIONS}
              placeholder="Locus"
              value={row.locus}
              onChange={(e) => updateRow(row.rowId, "locus", e.target.value)}
            />
            <InputField
              placeholder="Allele 1"
              value={row.allele1}
              onChange={(e) => updateRow(row.rowId, "allele1", e.target.value)}
            />
            <InputField
              placeholder="Allele 2"
              value={row.allele2}
              onChange={(e) => updateRow(row.rowId, "allele2", e.target.value)}
            />
            <button
              type="button"
              onClick={() => removeRow(row.rowId)}
              aria-label="Remove locus row"
              className="h-11 w-11 flex items-center justify-center text-text-muted hover:text-high-risk"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 mt-4">
        <Button type="button" variant="secondary" size="sm" onClick={addRow}>
          Add locus
        </Button>
        <Button type="button" size="sm" loading={isSaving} onClick={handleSave}>
          Save HLA typing
        </Button>
        {savedAt && !saveError && <span className="text-[13px] text-clear font-medium">Saved</span>}
      </div>

      {saveError && <p className="text-[13px] text-high-risk font-medium mt-2">{saveError}</p>}
    </Card>
  )
}
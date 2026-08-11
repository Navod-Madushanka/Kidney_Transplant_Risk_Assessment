// src/components/domain/reportFiles/ReportFilesCard.jsx
import { useState } from "react"
import Card from "../../ui/Card"
import FileUpload from "../../ui/FileUpload"
import Button from "../../ui/Button"
import Modal from "../../ui/Modal"

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * One dedicated, nullable slot for a single report category — at most one
 * file lives here at a time (the backend enforces this per (entity, category)
 * uniqueness). Uploading into a filled slot replaces the existing file.
 */
function ReportFileSlot({ category, label, existingFile, onUpload, onDelete, onDownload, onReplaced }) {
  const [pendingFile, setPendingFile] = useState(null)
  const [isReplacing, setIsReplacing] = useState(false)
  const [uploadFormKey, setUploadFormKey] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState("")

  const [confirmDelete, setConfirmDelete] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState("")

  const [isDownloading, setIsDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState("")

  async function handleUpload() {
    setUploadError("")
    if (!pendingFile) {
      setUploadError("Choose a file first.")
      return
    }

    setIsUploading(true)
    try {
      const created = await onUpload(category, pendingFile)
      onReplaced(created)
      setPendingFile(null)
      setIsReplacing(false)
      setUploadFormKey((prev) => prev + 1)
    } catch (err) {
      setUploadError(err.message || "Couldn't upload this file. Please try again.")
    } finally {
      setIsUploading(false)
    }
  }

  async function handleConfirmDelete() {
    setDeleteError("")
    setIsDeleting(true)
    try {
      await onDelete(existingFile.id)
      onReplaced(null)
      setConfirmDelete(false)
    } catch (err) {
      setDeleteError(err.message || "Couldn't delete this file. Please try again.")
    } finally {
      setIsDeleting(false)
    }
  }

  async function handleDownload() {
    setDownloadError("")
    setIsDownloading(true)
    try {
      await onDownload(existingFile.id, existingFile.original_filename)
    } catch (err) {
      setDownloadError(err.message || "Couldn't download this file. Please try again.")
    } finally {
      setIsDownloading(false)
    }
  }

  const showUploadForm = !existingFile || isReplacing

  return (
    <div className="rounded-lg border border-border p-3 flex flex-col gap-2.5">
      {existingFile && !isReplacing ? (
        <>
          <p className="text-[13px] font-semibold text-text">{label}</p>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[14px] text-text font-medium truncate">
                {existingFile.original_filename}
              </p>
              <p className="text-[13px] text-text-muted">{formatFileSize(existingFile.size_bytes)}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button type="button" variant="secondary" size="sm" loading={isDownloading} onClick={handleDownload}>
                Download
              </Button>
              <Button type="button" variant="secondary" size="sm" onClick={() => setIsReplacing(true)}>
                Replace
              </Button>
              <Button type="button" variant="destructive" size="sm" onClick={() => setConfirmDelete(true)}>
                Delete
              </Button>
            </div>
          </div>
        </>
      ) : null}

      {showUploadForm && (
        <div className="flex flex-col gap-2">
          <FileUpload
            key={uploadFormKey}
            label={label}
            accept="application/pdf,image/jpeg,image/png"
            onFileSelect={setPendingFile}
            helperText="PDF, JPG, or PNG"
          />
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" loading={isUploading} onClick={handleUpload}>
              {existingFile ? "Save replacement" : "Upload"}
            </Button>
            {isReplacing && (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  setIsReplacing(false)
                  setPendingFile(null)
                  setUploadError("")
                }}
              >
                Cancel
              </Button>
            )}
          </div>
        </div>
      )}

      {uploadError && <p className="text-[13px] text-high-risk font-medium">{uploadError}</p>}
      {downloadError && <p className="text-[13px] text-high-risk font-medium">{downloadError}</p>}

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Delete this file?">
        <p className="text-[15px] text-text-muted">This can&apos;t be undone.</p>
        {deleteError && <p className="text-[13px] text-high-risk font-medium mt-2">{deleteError}</p>}
        <div className="flex justify-end gap-2 mt-6">
          <Button type="button" variant="secondary" onClick={() => setConfirmDelete(false)}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" loading={isDeleting} onClick={handleConfirmDelete}>
            Delete
          </Button>
        </div>
      </Modal>
    </div>
  )
}

/**
 * loadState: "loading" | "loaded" | "error"
 *
 * Usage:
 *   <ReportFilesCard
 *     categories={PATIENT_REPORT_CATEGORY_OPTIONS}
 *     loadState={reportFilesState.state}
 *     existingFiles={reportFilesState.data}
 *     onUpload={(category, file) => uploadPatientReportFile(patient.id, category, file)}
 *     onDelete={(id) => deletePatientReportFile(patient.id, id)}
 *     onDownload={(id, filename) => downloadPatientReportFile(patient.id, id, filename)}
 *   />
 *
 * Reference storage only — uploading here never extracts or auto-fills any
 * clinical field, unlike the compatibility-check wizard's OCR photo step.
 *
 * One dedicated slot per report category rather than an open-ended list —
 * each slot is independently optional, and the backend enforces at most
 * one file per (record, category), replacing on re-upload. `categories`
 * is required rather than defaulting to "every category that exists":
 * the two joint lab documents (HLA typing, crossmatch) are owned by a
 * DonorPatientPair now, not a patient, so this card must only ever offer
 * the categories its caller's owner is actually allowed to hold (see
 * PAIR_REPORT_CATEGORY_OPTIONS / PATIENT_REPORT_CATEGORY_OPTIONS in
 * constants/reportFileCategory.js).
 */
export default function ReportFilesCard({
  categories,
  loadState,
  existingFiles = [],
  onUpload,
  onDelete,
  onDownload,
}) {
  const [overrides, setOverrides] = useState({})

  function filesByCategory(category) {
    if (category in overrides) return overrides[category]
    return existingFiles.find((f) => f.category === category) || null
  }

  function handleReplaced(category, file) {
    setOverrides((prev) => ({ ...prev, [category]: file }))
  }

  return (
    <Card>
      <Card.Header
        title="Report files"
        subtitle="One file per report type — lab documents attached to this record, for reference only"
      />

      {loadState === "loading" ? (
        <div className="flex justify-center py-6">
          <div className="h-6 w-6 rounded-full border-2 border-border border-t-accent animate-spin" role="status" aria-label="Loading" />
        </div>
      ) : loadState === "error" ? (
        <p className="text-[14px] text-text-muted">Couldn't load report files. Please refresh the page.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {categories.map(({ value, label }) => (
            <ReportFileSlot
              key={value}
              category={value}
              label={label}
              existingFile={filesByCategory(value)}
              onUpload={onUpload}
              onDelete={onDelete}
              onDownload={onDownload}
              onReplaced={(file) => handleReplaced(value, file)}
            />
          ))}
        </div>
      )}
    </Card>
  )
}

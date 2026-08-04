// src/components/domain/reportFiles/ReportFilesCard.jsx
import { useState } from "react"
import Card from "../../ui/Card"
import Select from "../../ui/Select"
import FileUpload from "../../ui/FileUpload"
import Button from "../../ui/Button"
import Modal from "../../ui/Modal"
import { REPORT_FILE_CATEGORY_OPTIONS, reportFileCategoryLabel } from "../../../constants/reportFileCategory"

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * loadState: "loading" | "loaded" | "error"
 *
 * Usage:
 *   <ReportFilesCard
 *     loadState={reportFilesState.state}
 *     existingFiles={reportFilesState.data}
 *     onUpload={(category, file) => uploadPatientReportFile(patient.id, category, file)}
 *     onDelete={(id) => deletePatientReportFile(patient.id, id)}
 *     onDownload={(id, filename) => downloadPatientReportFile(patient.id, id, filename)}
 *   />
 *
 * Reference storage only — uploading here never extracts or auto-fills any
 * clinical field, unlike the compatibility-check wizard's OCR photo step.
 */
export default function ReportFilesCard({ loadState, existingFiles = [], onUpload, onDelete, onDownload }) {
  const [category, setCategory] = useState("")
  const [file, setFile] = useState(null)
  const [uploadFormKey, setUploadFormKey] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState("")
  const [justUploaded, setJustUploaded] = useState([])

  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [deleteError, setDeleteError] = useState("")
  const [deletedIds, setDeletedIds] = useState(() => new Set())

  const [downloadingId, setDownloadingId] = useState(null)
  const [downloadError, setDownloadError] = useState("")

  async function handleUpload() {
    setUploadError("")
    if (!category || !file) {
      setUploadError("Choose a category and a file.")
      return
    }

    setIsUploading(true)
    try {
      const created = await onUpload(category, file)
      setJustUploaded((prev) => [created, ...prev])
      setCategory("")
      setFile(null)
      setUploadFormKey((prev) => prev + 1) // remounts FileUpload to clear its preview
    } catch (err) {
      setUploadError(err.message || "Couldn't upload this file. Please try again.")
    } finally {
      setIsUploading(false)
    }
  }

  async function handleConfirmDelete(id) {
    setDeleteError("")
    setDeletingId(id)
    try {
      await onDelete(id)
      setDeletedIds((prev) => new Set(prev).add(id))
      setConfirmDeleteId(null)
    } catch (err) {
      setDeleteError(err.message || "Couldn't delete this file. Please try again.")
    } finally {
      setDeletingId(null)
    }
  }

  async function handleDownload(id, filename) {
    setDownloadError("")
    setDownloadingId(id)
    try {
      await onDownload(id, filename)
    } catch (err) {
      setDownloadError(err.message || "Couldn't download this file. Please try again.")
    } finally {
      setDownloadingId(null)
    }
  }

  const visibleFiles = [...justUploaded, ...existingFiles].filter((f) => !deletedIds.has(f.id))

  return (
    <Card>
      <Card.Header
        title="Report files"
        subtitle="Lab documents attached to this record — for reference only"
      />

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-end mb-4">
        <Select
          label="Category"
          placeholder="Select category"
          options={REPORT_FILE_CATEGORY_OPTIONS}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
        <FileUpload
          key={uploadFormKey}
          label="File"
          accept="application/pdf,image/jpeg,image/png"
          onFileSelect={setFile}
          helperText="PDF, JPG, or PNG"
        />
        <Button type="button" size="sm" loading={isUploading} onClick={handleUpload}>
          Upload
        </Button>
      </div>

      {uploadError && <p className="text-[13px] text-high-risk font-medium mb-3">{uploadError}</p>}
      {downloadError && <p className="text-[13px] text-high-risk font-medium mb-3">{downloadError}</p>}

      {loadState === "loading" ? (
        <div className="flex justify-center py-6">
          <div className="h-6 w-6 rounded-full border-2 border-border border-t-accent animate-spin" role="status" aria-label="Loading" />
        </div>
      ) : loadState === "error" ? (
        <p className="text-[14px] text-text-muted">Couldn't load report files. Please refresh the page.</p>
      ) : visibleFiles.length === 0 ? (
        <p className="text-[14px] text-text-muted">No report files attached yet.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {visibleFiles.map((f) => (
            <li key={f.id} className="py-2.5 flex items-center justify-between gap-3 text-[14px]">
              <div className="min-w-0">
                <p className="text-text font-medium truncate">{f.original_filename}</p>
                <p className="text-[13px] text-text-muted">
                  {reportFileCategoryLabel(f.category)} · {formatFileSize(f.size_bytes)}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={downloadingId === f.id}
                  onClick={() => handleDownload(f.id, f.original_filename)}
                >
                  Download
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={() => setConfirmDeleteId(f.id)}
                >
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={confirmDeleteId !== null}
        onClose={() => setConfirmDeleteId(null)}
        title="Delete this file?"
      >
        <p className="text-[15px] text-text-muted">This can&apos;t be undone.</p>
        {deleteError && <p className="text-[13px] text-high-risk font-medium mt-2">{deleteError}</p>}
        <div className="flex justify-end gap-2 mt-6">
          <Button type="button" variant="secondary" onClick={() => setConfirmDeleteId(null)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            loading={deletingId === confirmDeleteId}
            onClick={() => handleConfirmDelete(confirmDeleteId)}
          >
            Delete
          </Button>
        </div>
      </Modal>
    </Card>
  )
}

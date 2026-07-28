// src/components/ui/FileUpload.jsx
import { useId, useRef, useState } from "react"

/**
 * Usage:
 *   <FileUpload
 *     label="Upload bead-specificity chart"
 *     accept="image/*"
 *     onFileSelect={(file) => setSelectedFile(file)}
 *     helperText="JPG or PNG, up to 10MB"
 *   />
 *
 *   // Controlled from external state (e.g. a wizard step navigated back to):
 *   <FileUpload
 *     label="HLA Typing Report"
 *     initialFile={wizardState.photos.hlaTypingReport}
 *     onFileSelect={(file) => actions.setPhoto("hlaTypingReport", file)}
 *   />
 *
 * Supports drag-and-drop and tap-to-browse (works fine on mobile, where drag
 * just won't trigger and the tap target takes over). Shows a lightweight
 * preview once a file is chosen, with a way to clear and re-select.
 *
 * initialFile is optional and only needed when the selection can outlive
 * this component's mount (e.g. wizard steps you navigate away from and back
 * to). It seeds the initial preview and stays in sync if the caller changes
 * it externally (including clearing it back to null, e.g. on a form reset).
 * Purely internal selections (the common case) don't need it at all.
 */
export default function FileUpload({
  label,
  accept = "image/*",
  onFileSelect,
  helperText,
  error,
  initialFile = null,
  className = "",
}) {
  const inputId = useId()
  const inputRef = useRef(null)
  const [selectedFile, setSelectedFile] = useState(initialFile)
  const [isDragActive, setIsDragActive] = useState(false)

  // Keep the preview in sync with externally-owned state (e.g. wizard
  // context). This uses React's documented "adjust state during render"
  // pattern (https://react.dev/reference/react/useState#storing-information-from-previous-renders)
  // rather than a useEffect — setting state directly inside an effect body
  // causes an extra render-then-effect cascade (and a brief flash of stale
  // content); adjusting during render applies in the same render initialFile
  // changes in. Doesn't fire on purely-internal selections, since those
  // already update selectedFile directly in handleFiles/handleClear.
  const [prevInitialFile, setPrevInitialFile] = useState(initialFile)
  if (initialFile !== prevInitialFile) {
    setPrevInitialFile(initialFile)
    setSelectedFile(initialFile)
  }

  function handleFiles(fileList) {
    const file = fileList?.[0]
    if (!file) return
    setSelectedFile(file)
    onFileSelect?.(file)
  }

  function handleClear() {
    setSelectedFile(null)
    if (inputRef.current) inputRef.current.value = ""
    onFileSelect?.(null)
  }

  return (
    <div className={["flex flex-col gap-1.5", className].join(" ")}>
      {label && (
        <label htmlFor={inputId} className="text-[13px] font-semibold text-text">
          {label}
        </label>
      )}

      {!selectedFile ? (
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setIsDragActive(true)
          }}
          onDragLeave={() => setIsDragActive(false)}
          onDrop={(e) => {
            e.preventDefault()
            setIsDragActive(false)
            handleFiles(e.dataTransfer.files)
          }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") inputRef.current?.click()
          }}
          className={[
            "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-colors",
            isDragActive ? "border-accent bg-accent-subtle" : "border-border bg-bg",
            error ? "border-high-risk" : "",
          ].join(" ")}
        >
          <svg className="h-8 w-8 text-text-muted" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M12 16V4m0 0L7 9m5-5l5 5M5 20h14"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <p className="text-[14px] text-text font-medium">
            Tap to upload, or drag a file here
          </p>
          {helperText && <p className="text-[13px] text-text-muted">{helperText}</p>}
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            accept={accept}
            className="sr-only"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3">
          <div className="flex items-center gap-3 min-w-0">
            <svg className="h-8 w-8 shrink-0 text-accent" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M4 4h10l6 6v10a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1z"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
            </svg>
            <span className="text-[14px] text-text truncate">{selectedFile.name}</span>
          </div>
          <button
            type="button"
            onClick={handleClear}
            className="text-[13px] font-semibold text-accent hover:text-accent-hover shrink-0"
          >
            Remove
          </button>
        </div>
      )}

      {error && <p className="text-[13px] text-high-risk font-medium">{error}</p>}
    </div>
  )
}
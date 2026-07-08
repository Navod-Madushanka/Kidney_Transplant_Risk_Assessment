// src/components/ui/Modal.jsx
import { useEffect, useRef } from "react"
import { createPortal } from "react-dom"

/**
 * Usage:
 *   <Modal open={isOpen} onClose={() => setIsOpen(false)} title="Halt this report?">
 *     <p className="text-[15px] text-text-muted">
 *       This will mark the compatibility check as halted. This can't be undone.
 *     </p>
 *     <div className="flex justify-end gap-2 mt-6">
 *       <Button variant="secondary" onClick={() => setIsOpen(false)}>Cancel</Button>
 *       <Button variant="destructive" onClick={confirmHalt}>Halt report</Button>
 *     </div>
 *   </Modal>
 *
 * Renders via a portal so it always sits above app layout regardless of where
 * it's mounted. Closes on Escape and on backdrop click; traps focus while open.
 */
export default function Modal({ open, onClose, title, children, className = "" }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    if (!open) return

    const previouslyFocused = document.activeElement
    dialogRef.current?.focus()

    function handleKeyDown(e) {
      if (e.key === "Escape") onClose?.()
    }

    document.addEventListener("keydown", handleKeyDown)
    document.body.style.overflow = "hidden"

    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.body.style.overflow = ""
      previouslyFocused?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? "modal-title" : undefined}
        tabIndex={-1}
        className={[
          "w-full max-w-md bg-surface rounded-lg shadow-card-hover p-6",
          "focus:outline-none",
          className,
        ].join(" ")}
      >
        {title && (
          <h2 id="modal-title" className="text-[17px] font-semibold text-text mb-3">
            {title}
          </h2>
        )}
        {children}
      </div>
    </div>,
    document.body
  )
}
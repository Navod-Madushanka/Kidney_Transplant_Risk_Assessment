// src/components/domain/reportFiles/ReportFilesCard.test.jsx
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import ReportFilesCard from "./ReportFilesCard"

const HLA_FILE = {
  id: "file-1",
  category: "hla_typing_report",
  original_filename: "typing.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  created_at: "2026-08-01T00:00:00Z",
}

function renderCard(overrides = {}) {
  const props = {
    loadState: "loaded",
    existingFiles: [HLA_FILE],
    onUpload: vi.fn(),
    onDelete: vi.fn(),
    onDownload: vi.fn(),
    ...overrides,
  }
  return { ...render(<ReportFilesCard {...props} />), props }
}

function slotFor(label) {
  return screen.getByText(label).closest("div.rounded-lg")
}

describe("ReportFilesCard", () => {
  it("renders one dedicated slot per report category", () => {
    renderCard({ existingFiles: [] })

    expect(screen.getByLabelText("HLA Typing Report")).toBeInTheDocument()
    expect(screen.getByLabelText("Crossmatch Report")).toBeInTheDocument()
    expect(screen.getByLabelText("Bead Specificity Chart — Page 1")).toBeInTheDocument()
    expect(screen.getByLabelText("Bead Specificity Chart — Page 2")).toBeInTheDocument()
    expect(screen.getByLabelText("Other")).toBeInTheDocument()
  })

  it("shows an existing file in its matching category slot only", () => {
    renderCard()

    const hlaSlot = slotFor("HLA Typing Report")
    expect(within(hlaSlot).getByText("typing.pdf")).toBeInTheDocument()
    expect(within(hlaSlot).getByText(/2\.0 KB/)).toBeInTheDocument()

    // Empty slots still render their upload picker instead of a file summary.
    expect(screen.getByLabelText("Crossmatch Report")).toBeInTheDocument()
  })

  it("shows the loading state", () => {
    renderCard({ loadState: "loading", existingFiles: [] })
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument()
  })

  it("shows the error state", () => {
    renderCard({ loadState: "error", existingFiles: [] })
    expect(screen.getByText(/Couldn't load report files/)).toBeInTheDocument()
  })

  it("uploads into an empty slot and shows it there without a full re-fetch", async () => {
    const user = userEvent.setup()
    const created = {
      id: "file-2",
      category: "crossmatch_report",
      original_filename: "crossmatch.pdf",
      content_type: "application/pdf",
      size_bytes: 512,
      created_at: "2026-08-01T01:00:00Z",
    }
    const onUpload = vi.fn().mockResolvedValue(created)
    renderCard({ onUpload })

    const file = new File(["fake bytes"], "crossmatch.pdf", { type: "application/pdf" })
    await user.upload(screen.getByLabelText("Crossmatch Report"), file)

    const crossmatchSlot = slotFor("Crossmatch Report")
    await user.click(within(crossmatchSlot).getByRole("button", { name: "Upload" }))

    await waitFor(() =>
      expect(onUpload).toHaveBeenCalledWith("crossmatch_report", expect.any(File))
    )
    expect(await screen.findByText("crossmatch.pdf")).toBeInTheDocument()
    // The HLA slot (a separate category) is untouched.
    expect(screen.getByText("typing.pdf")).toBeInTheDocument()
  })

  it("shows an error and keeps the slot empty when upload fails", async () => {
    const user = userEvent.setup()
    const onUpload = vi.fn().mockRejectedValue(new Error("upload failed"))
    renderCard({ onUpload, existingFiles: [] })

    const file = new File(["fake bytes"], "crossmatch.pdf", { type: "application/pdf" })
    await user.upload(screen.getByLabelText("Crossmatch Report"), file)
    const crossmatchSlot = slotFor("Crossmatch Report")
    await user.click(within(crossmatchSlot).getByRole("button", { name: "Upload" }))

    expect(await screen.findByText("upload failed")).toBeInTheDocument()
    // FileUpload keeps the picked file selected in its own preview so the
    // doctor can retry without re-choosing it — only assert the slot never
    // switched into its "saved" summary state (no Download/Delete controls).
    expect(within(crossmatchSlot).queryByRole("button", { name: "Download" })).not.toBeInTheDocument()
  })

  it("requires a file before uploading", async () => {
    const user = userEvent.setup()
    const onUpload = vi.fn()
    renderCard({ onUpload, existingFiles: [] })

    const crossmatchSlot = slotFor("Crossmatch Report")
    await user.click(within(crossmatchSlot).getByRole("button", { name: "Upload" }))

    expect(await screen.findByText("Choose a file first.")).toBeInTheDocument()
    expect(onUpload).not.toHaveBeenCalled()
  })

  it("replaces the file in a filled slot, discarding the previous one", async () => {
    const user = userEvent.setup()
    const replacement = {
      id: "file-3",
      category: "hla_typing_report",
      original_filename: "typing-v2.pdf",
      content_type: "application/pdf",
      size_bytes: 4096,
      created_at: "2026-08-02T00:00:00Z",
    }
    const onUpload = vi.fn().mockResolvedValue(replacement)
    renderCard({ onUpload })

    let hlaSlot = slotFor("HLA Typing Report")
    await user.click(within(hlaSlot).getByRole("button", { name: "Replace" }))

    hlaSlot = slotFor("HLA Typing Report")
    const file = new File(["v2 bytes"], "typing-v2.pdf", { type: "application/pdf" })
    await user.upload(within(hlaSlot).getByLabelText("HLA Typing Report"), file)
    await user.click(within(hlaSlot).getByRole("button", { name: "Save replacement" }))

    await waitFor(() =>
      expect(onUpload).toHaveBeenCalledWith("hla_typing_report", expect.any(File))
    )
    expect(await screen.findByText("typing-v2.pdf")).toBeInTheDocument()
    expect(screen.queryByText("typing.pdf")).not.toBeInTheDocument()
  })

  it("cancels a replace without calling onUpload, keeping the original file", async () => {
    const user = userEvent.setup()
    const onUpload = vi.fn()
    renderCard({ onUpload })

    let hlaSlot = slotFor("HLA Typing Report")
    await user.click(within(hlaSlot).getByRole("button", { name: "Replace" }))

    hlaSlot = slotFor("HLA Typing Report")
    await user.click(within(hlaSlot).getByRole("button", { name: "Cancel" }))

    expect(onUpload).not.toHaveBeenCalled()
    expect(screen.getByText("typing.pdf")).toBeInTheDocument()
  })

  it("deletes a file after confirming in the modal, reopening the slot for upload", async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn().mockResolvedValue(undefined)
    renderCard({ onDelete })

    const hlaSlot = slotFor("HLA Typing Report")
    await user.click(within(hlaSlot).getByRole("button", { name: "Delete" }))
    const dialog = screen.getByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "Delete" }))

    await waitFor(() => expect(onDelete).toHaveBeenCalledWith("file-1"))
    await waitFor(() => expect(screen.queryByText("typing.pdf")).not.toBeInTheDocument())
    expect(screen.getByLabelText("HLA Typing Report")).toBeInTheDocument()
  })

  it("keeps the file when the delete confirmation is cancelled", async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    renderCard({ onDelete })

    const hlaSlot = slotFor("HLA Typing Report")
    await user.click(within(hlaSlot).getByRole("button", { name: "Delete" }))
    await user.click(screen.getByRole("button", { name: "Cancel" }))

    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.getByText("typing.pdf")).toBeInTheDocument()
  })

  it("calls onDownload with the file id and original filename", async () => {
    const user = userEvent.setup()
    const onDownload = vi.fn().mockResolvedValue(undefined)
    renderCard({ onDownload })

    const hlaSlot = slotFor("HLA Typing Report")
    await user.click(within(hlaSlot).getByRole("button", { name: "Download" }))

    await waitFor(() => expect(onDownload).toHaveBeenCalledWith("file-1", "typing.pdf"))
  })
})

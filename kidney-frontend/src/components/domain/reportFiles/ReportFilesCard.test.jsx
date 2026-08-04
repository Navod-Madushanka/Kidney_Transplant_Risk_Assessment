// src/components/domain/reportFiles/ReportFilesCard.test.jsx
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import ReportFilesCard from "./ReportFilesCard"

const EXISTING_FILE = {
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
    existingFiles: [EXISTING_FILE],
    onUpload: vi.fn(),
    onDelete: vi.fn(),
    onDownload: vi.fn(),
    ...overrides,
  }
  return { ...render(<ReportFilesCard {...props} />), props }
}

async function selectCategoryAndFile(user, category = "crossmatch_report") {
  await user.selectOptions(screen.getByLabelText("Category"), category)
  const file = new File(["fake bytes"], "crossmatch.pdf", { type: "application/pdf" })
  await user.upload(screen.getByLabelText("File"), file)
  return file
}

describe("ReportFilesCard", () => {
  it("renders existing files with category, filename, and formatted size", () => {
    renderCard()

    const row = screen.getByText("typing.pdf").closest("li")
    expect(within(row).getByText(/HLA Typing Report/)).toBeInTheDocument()
    expect(within(row).getByText(/2\.0 KB/)).toBeInTheDocument()
  })

  it("shows the loading state", () => {
    renderCard({ loadState: "loading", existingFiles: [] })
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument()
  })

  it("shows the error state", () => {
    renderCard({ loadState: "error", existingFiles: [] })
    expect(screen.getByText(/Couldn't load report files/)).toBeInTheDocument()
  })

  it("shows an empty-state message when there are no files", () => {
    renderCard({ existingFiles: [] })
    expect(screen.getByText("No report files attached yet.")).toBeInTheDocument()
  })

  it("uploads a file and prepends it to the list without a full re-fetch", async () => {
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

    await selectCategoryAndFile(user)
    await user.click(screen.getByRole("button", { name: "Upload" }))

    await waitFor(() =>
      expect(onUpload).toHaveBeenCalledWith("crossmatch_report", expect.any(File))
    )
    expect(await screen.findByText("crossmatch.pdf")).toBeInTheDocument()
    expect(screen.getByText("typing.pdf")).toBeInTheDocument()
  })

  it("shows an error and adds no row when upload fails", async () => {
    const user = userEvent.setup()
    const onUpload = vi.fn().mockRejectedValue(new Error("upload failed"))
    renderCard({ onUpload })

    await selectCategoryAndFile(user)
    await user.click(screen.getByRole("button", { name: "Upload" }))

    expect(await screen.findByText("upload failed")).toBeInTheDocument()
    // The file stays selected in the picker so the doctor can retry without
    // re-choosing it — only assert no *new row* was added to the list.
    const list = screen.getByRole("list")
    expect(within(list).queryByText("crossmatch.pdf")).not.toBeInTheDocument()
  })

  it("requires both a category and a file before uploading", async () => {
    const user = userEvent.setup()
    const onUpload = vi.fn()
    renderCard({ onUpload })

    await user.click(screen.getByRole("button", { name: "Upload" }))

    expect(await screen.findByText("Choose a category and a file.")).toBeInTheDocument()
    expect(onUpload).not.toHaveBeenCalled()
  })

  it("deletes a file after confirming in the modal", async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn().mockResolvedValue(undefined)
    renderCard({ onDelete })

    await user.click(screen.getByRole("button", { name: "Delete" }))
    const dialog = screen.getByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "Delete" }))

    await waitFor(() => expect(onDelete).toHaveBeenCalledWith("file-1"))
    await waitFor(() => expect(screen.queryByText("typing.pdf")).not.toBeInTheDocument())
  })

  it("keeps the file when the delete confirmation is cancelled", async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    renderCard({ onDelete })

    await user.click(screen.getByRole("button", { name: "Delete" }))
    await user.click(screen.getByRole("button", { name: "Cancel" }))

    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.getByText("typing.pdf")).toBeInTheDocument()
  })

  it("calls onDownload with the file id and original filename", async () => {
    const user = userEvent.setup()
    const onDownload = vi.fn().mockResolvedValue(undefined)
    renderCard({ onDownload })

    await user.click(screen.getByRole("button", { name: "Download" }))

    await waitFor(() => expect(onDownload).toHaveBeenCalledWith("file-1", "typing.pdf"))
  })
})

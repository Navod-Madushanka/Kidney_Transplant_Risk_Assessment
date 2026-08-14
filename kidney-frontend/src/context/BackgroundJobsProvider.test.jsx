// src/context/BackgroundJobsProvider.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { getExtractionJob } from "../api/ocr"
import { BackgroundJobsProvider } from "./BackgroundJobsProvider"
import { useBackgroundJobs } from "../hooks/useBackgroundJobs"

vi.mock("../api/ocr", () => ({ getExtractionJob: vi.fn() }))

const LABEL = "Bead specificity chart — Alice Patient"

function StartJobButton() {
  const { startJob } = useBackgroundJobs()
  return (
    <button
      onClick={() =>
        startJob({
          jobId: "job-1",
          label: LABEL,
          documentSlots: [{ documentType: "bead_specificity_page_1" }],
        })
      }
    >
      Start job
    </button>
  )
}

function renderProvider() {
  return render(
    <BackgroundJobsProvider>
      <StartJobButton />
    </BackgroundJobsProvider>
  )
}

describe("BackgroundJobsProvider", () => {
  it("polls a started job to completion and shows a done state in the toast", async () => {
    const user = userEvent.setup()
    getExtractionJob.mockResolvedValue({
      job_id: "job-1",
      status: "done",
      documents: { bead_specificity_page_1: { status: "done", completed: 3, total: 3 } },
      error: null,
    })

    renderProvider()
    await user.click(screen.getByRole("button", { name: "Start job" }))

    expect(await screen.findByText(LABEL)).toBeInTheDocument()
    expect(await screen.findByText(/Done — review it/)).toBeInTheDocument()
  })

  it("shows the job's own failure message when it fails server-side", async () => {
    const user = userEvent.setup()
    getExtractionJob.mockResolvedValue({
      job_id: "job-1",
      status: "failed",
      documents: {},
      error: "Ollama unreachable",
    })

    renderProvider()
    await user.click(screen.getByRole("button", { name: "Start job" }))

    expect(await screen.findByText("Ollama unreachable")).toBeInTheDocument()
  })

  it("stays visible across re-renders and can be dismissed manually", async () => {
    const user = userEvent.setup()
    getExtractionJob.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      documents: {},
      error: null,
    })

    renderProvider()
    await user.click(screen.getByRole("button", { name: "Start job" }))
    expect(await screen.findByText(LABEL)).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Dismiss" }))
    expect(screen.queryByText(LABEL)).not.toBeInTheDocument()
  })

  it("renders nothing when there are no active jobs", () => {
    renderProvider()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})

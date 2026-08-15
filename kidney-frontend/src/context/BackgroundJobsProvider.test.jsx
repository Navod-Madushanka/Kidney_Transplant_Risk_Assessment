// src/context/BackgroundJobsProvider.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
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

  // Part H fix: a doctor double-clicking Register (or anything else that
  // calls startJob twice) before the first click's request resolves used
  // to register the same jobId twice, giving it two independent
  // JobPollers each polling at the intended cadence -- 2x the intended
  // request rate, worse under exactly the backend load this Part fixes.
  it("does not register a second poller when startJob is called twice with the same jobId", async () => {
    const user = userEvent.setup()
    // This file's other tests share the same module-level getExtractionJob
    // mock and don't reset its call history -- harmless for them (none
    // assert an exact count), but this test does, so it needs a clean
    // slate.
    getExtractionJob.mockClear()
    getExtractionJob.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      documents: {},
      error: null,
    })

    renderProvider()
    await user.click(screen.getByRole("button", { name: "Start job" }))
    await user.click(screen.getByRole("button", { name: "Start job" }))

    expect(await screen.findByText(LABEL)).toBeInTheDocument()
    // One toast entry, not two, despite two startJob calls.
    expect(screen.getAllByText(LABEL)).toHaveLength(1)

    // One poller means one call to getExtractionJob per tick -- two would
    // mean two independent JobPoller instances both hit it.
    await waitFor(() => expect(getExtractionJob).toHaveBeenCalledTimes(1))
  })
})

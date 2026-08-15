// src/hooks/useExtractionJobPolling.test.jsx
//
// Part H fix: a failed poll used to retry on a fixed 2.5s cadence forever,
// with no backoff and no signal to the doctor -- under real backend load
// (e.g. the connection-pool exhaustion this Part H fixes -- see
// ocr_job_service.run_extraction_job's docstring in kidney-backend) every
// open tab hammering a struggling server at a fixed interval made things
// worse, not better. Uses vitest's fake timers to assert the exact backoff
// schedule without a real multi-second wait.
import { act, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { getExtractionJob } from "../api/ocr"
import { useExtractionJobPolling } from "./useExtractionJobPolling"

vi.mock("../api/ocr", () => ({ getExtractionJob: vi.fn() }))

function Harness({ jobId, status, onStatusChange, onPollingStalled }) {
  useExtractionJobPolling({ jobId, status, onStatusChange, onPollingStalled })
  return null
}

async function advance(ms) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe("useExtractionJobPolling", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it("backs off after a failure instead of retrying at the normal 2.5s cadence", async () => {
    getExtractionJob.mockRejectedValue(new Error("network down"))

    render(<Harness jobId="job-1" status="running" onStatusChange={() => {}} />)
    // The first poll fires synchronously on mount, no timer involved.
    expect(getExtractionJob).toHaveBeenCalledTimes(1)

    // A normal (non-backed-off) retry would fire at 2.5s -- confirm it does
    // NOT fire that early after a failure.
    await advance(2500)
    expect(getExtractionJob).toHaveBeenCalledTimes(1)

    // The backed-off retry (2.5s * 2^1 = 5s) fires at 5s.
    await advance(2500)
    expect(getExtractionJob).toHaveBeenCalledTimes(2)
  })

  it("does not mark the job failed and does not report stalled before the failure threshold", async () => {
    getExtractionJob.mockRejectedValue(new Error("network down"))
    const onStatusChange = vi.fn()
    const onPollingStalled = vi.fn()

    render(
      <Harness
        jobId="job-1"
        status="running"
        onStatusChange={onStatusChange}
        onPollingStalled={onPollingStalled}
      />
    )

    // The mount-time poll is failure #1; two more (at +5s, +10s) make 3
    // total -- one short of the 4-failure threshold.
    await advance(5000)
    await advance(10000)
    expect(getExtractionJob).toHaveBeenCalledTimes(3)

    expect(onPollingStalled).not.toHaveBeenCalled()
    // A poll request failing must never surface as the job itself
    // failing -- the job is very likely still running server-side.
    expect(onStatusChange).not.toHaveBeenCalled()
  })

  it("reports stalled after 4 consecutive failures, still without marking the job failed, and clears on recovery", async () => {
    getExtractionJob.mockRejectedValue(new Error("network down"))
    const onStatusChange = vi.fn()
    const onPollingStalled = vi.fn()

    render(
      <Harness
        jobId="job-1"
        status="running"
        onStatusChange={onStatusChange}
        onPollingStalled={onPollingStalled}
      />
    )

    // Mount-time poll is failure #1; +5s/+10s/+20s make failures #2/#3/#4
    // -- #4 is what crosses STALLED_AFTER_FAILURES.
    await advance(5000)
    await advance(10000)
    await advance(20000)
    expect(getExtractionJob).toHaveBeenCalledTimes(4)

    expect(onPollingStalled).toHaveBeenCalledTimes(1)
    expect(onPollingStalled).toHaveBeenCalledWith(true)
    expect(onStatusChange).not.toHaveBeenCalled()

    // Backoff caps at 30s, not 40s (2.5s * 2^4) -- the retry scheduled
    // after the 4th failure still fires at +30s, not later.
    getExtractionJob.mockResolvedValue({ status: "running", documents: {}, error: null })
    await advance(30000)
    expect(getExtractionJob).toHaveBeenCalledTimes(5)

    // Recovered -- told explicitly, and the cadence resets to the normal
    // 2.5s rather than staying backed off.
    expect(onPollingStalled).toHaveBeenCalledTimes(2)
    expect(onPollingStalled).toHaveBeenLastCalledWith(false)
    expect(onStatusChange).toHaveBeenCalledWith("running", {}, null)

    await advance(2500)
    expect(getExtractionJob).toHaveBeenCalledTimes(6)
  })
})

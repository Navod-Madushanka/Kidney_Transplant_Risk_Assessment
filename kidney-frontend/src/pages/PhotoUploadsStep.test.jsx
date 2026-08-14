// src/pages/PhotoUploadsStep.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { WizardProvider } from "../context/WizardProvider"
import { useWizard } from "../hooks/useWizard"
import { startExtractionJob, getExtractionJob } from "../api/ocr"
import PhotoUploadsStep from "./PhotoUploadsStep"

vi.mock("../api/ocr", () => ({
  startExtractionJob: vi.fn(),
  getExtractionJob: vi.fn(),
}))

// Renders alongside PhotoUploadsStep, under the same WizardProvider, so
// tests can observe that extraction results actually landed in the
// wizard's shared fields -- not just in PhotoUploadsStep's own UI -- which
// is the whole point of extraction living in wizard context instead of
// page-local state (see wizardReducer.js's `extraction` field and
// useExtractionJobPolling.js).
function PatientNamePeek() {
  const { state } = useWizard()
  return <div data-testid="patient-name-peek">{state.patient_details.full_name}</div>
}

function renderStep({ initialEntry = "/checks/new/photos" } = {}) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <WizardProvider>
        <Routes>
          <Route path="/checks/new/photos" element={<PhotoUploadsStep />} />
          <Route path="/checks/new/subject" element={<div>Subject Step</div>} />
        </Routes>
        <PatientNamePeek />
      </WizardProvider>
    </MemoryRouter>
  )
}

async function uploadHlaTypingReport(user) {
  const file = new File(["x"], "hla.jpg", { type: "image/jpeg" })
  await user.upload(screen.getByLabelText("HLA Typing Report"), file)
}

function jobStatus(status, documents) {
  return { job_id: "job-1", status, documents, error: null }
}

const DONE_DOCUMENT = {
  status: "done",
  completed: 1,
  total: 1,
  patient_details: { full_name: "Rev.A.Premarathna Thero" },
  donor_details: {},
  patient_hla: [],
  donor_hla: [],
  bead_specificity: [],
  crossmatch: {},
  errors: [],
}

describe("PhotoUploadsStep", () => {
  it("starts a job, polls it to completion, and hydrates the wizard's shared fields", async () => {
    const user = userEvent.setup()
    startExtractionJob.mockResolvedValue({ job_id: "job-1" })
    getExtractionJob.mockResolvedValue(
      jobStatus("done", { hla_typing_report: DONE_DOCUMENT })
    )

    renderStep()
    await uploadHlaTypingReport(user)
    await user.click(screen.getByRole("button", { name: /extract from documents/i }))

    expect(startExtractionJob).toHaveBeenCalledWith(expect.objectContaining({ hlaTypingReport: expect.any(File) }))
    expect(
      await screen.findByText("Extracted — review the details in the next steps")
    ).toBeInTheDocument()
    // The actual regression this replaces: extraction results must reach
    // the wizard's shared state, not just PhotoUploadsStep's own display.
    expect(await screen.findByTestId("patient-name-peek")).toHaveTextContent(
      "Rev.A.Premarathna Thero"
    )
  })

  it("shows real tile-by-tile percentage while a document is still in progress", async () => {
    const user = userEvent.setup()
    startExtractionJob.mockResolvedValue({ job_id: "job-1" })
    getExtractionJob.mockResolvedValue(
      jobStatus("running", {
        bead_specificity_page_1: {
          status: "in_progress",
          completed: 3,
          total: 8,
          patient_details: {},
          donor_details: {},
          patient_hla: [],
          donor_hla: [],
          bead_specificity: [],
          crossmatch: {},
          errors: [],
        },
      })
    )

    renderStep()
    await user.upload(
      screen.getByLabelText("Bead Specificity Chart — Page 1"),
      new File(["x"], "bead1.jpg", { type: "image/jpeg" })
    )
    await user.click(screen.getByRole("button", { name: /extract from documents/i }))

    expect(await screen.findByText("3/8 sections — 38%")).toBeInTheDocument()
  })

  it("keeps extracting and hydrates the wizard even after navigating to another wizard step", async () => {
    // This is the bug being fixed: clicking Continue used to unmount the
    // component holding all extraction state, silently killing every
    // visible sign of progress. Extraction now lives in wizard context
    // (polled from WizardProvider, not PhotoUploadsStep), so it must keep
    // running and land its results in shared state even while a different
    // step is on screen.
    const user = userEvent.setup()
    startExtractionJob.mockResolvedValue({ job_id: "job-1" })
    getExtractionJob.mockResolvedValue(
      jobStatus("done", { hla_typing_report: DONE_DOCUMENT })
    )

    renderStep()
    await uploadHlaTypingReport(user)
    await user.click(screen.getByRole("button", { name: /extract from documents/i }))
    await user.click(screen.getByRole("button", { name: "Continue", exact: true }))

    expect(await screen.findByText("Subject Step")).toBeInTheDocument()
    expect(await screen.findByTestId("patient-name-peek")).toHaveTextContent(
      "Rev.A.Premarathna Thero"
    )
  })

  it("shows an error and lets the doctor retry if the job fails to start", async () => {
    const user = userEvent.setup()
    startExtractionJob.mockRejectedValue(new Error("Couldn't reach the server"))

    renderStep()
    await uploadHlaTypingReport(user)
    await user.click(screen.getByRole("button", { name: /extract from documents/i }))

    expect(await screen.findByText("Couldn't reach the server")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /extract from documents/i })).toBeEnabled()
  })

  it("surfaces per-document warnings from the polled job", async () => {
    const user = userEvent.setup()
    startExtractionJob.mockResolvedValue({ job_id: "job-1" })
    getExtractionJob.mockResolvedValue(
      jobStatus("done", {
        hla_typing_report: {
          ...DONE_DOCUMENT,
          errors: [{ field: "hla_typing_report", message: "model_returned_unrecognized_locus:X" }],
        },
      })
    )

    renderStep()
    await uploadHlaTypingReport(user)
    await user.click(screen.getByRole("button", { name: /extract from documents/i }))

    expect(await screen.findByText(/model_returned_unrecognized_locus:X/)).toBeInTheDocument()
  })

  it("navigates to the subject step on Continue without requiring extraction", async () => {
    const user = userEvent.setup()

    renderStep()
    // exact:true matters here — a loose /continue/i also matches the Page 2
    // FileUpload's helper text ("...chart continues...").
    await user.click(screen.getByRole("button", { name: "Continue", exact: true }))

    expect(await screen.findByText("Subject Step")).toBeInTheDocument()
  })

  // Regression coverage for NewCheckFromRecordsPage.jsx: it navigates here
  // with `state: { prefillPhotos }` so a doctor starting a check from an
  // existing patient/donor's archived report files sees the slots already
  // filled in, same as if they'd picked the files by hand.
  it("pre-fills photo slots from router state when arriving from the 'start from records' page", async () => {
    const prefillFile = new File(["x"], "typing.pdf", { type: "application/pdf" })

    render(
      <MemoryRouter
        initialEntries={[
          { pathname: "/checks/new/photos", state: { prefillPhotos: { hlaTypingReport: prefillFile } } },
        ]}
      >
        <WizardProvider>
          <Routes>
            <Route path="/checks/new/photos" element={<PhotoUploadsStep />} />
          </Routes>
        </WizardProvider>
      </MemoryRouter>
    )

    expect(await screen.findByText("typing.pdf")).toBeInTheDocument()
    // The other three slots weren't included in prefillPhotos, so they stay
    // empty upload pickers rather than erroring out on the missing keys.
    expect(screen.getByLabelText("Crossmatch Report")).toBeInTheDocument()
  })
})

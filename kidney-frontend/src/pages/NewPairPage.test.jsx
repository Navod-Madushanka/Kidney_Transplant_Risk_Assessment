// src/pages/NewPairPage.test.jsx
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { startExtractionJob, getExtractionJob } from "../api/ocr"
import { createPair } from "../api/pairs"
import { uploadPairReportFile, uploadPatientReportFile } from "../api/reportFiles"
import { BackgroundJobsProvider } from "../context/BackgroundJobsProvider"
import NewPairPage from "./NewPairPage"

vi.mock("../api/ocr", () => ({
  startExtractionJob: vi.fn(),
  getExtractionJob: vi.fn(),
}))
vi.mock("../api/pairs", () => ({ createPair: vi.fn() }))
vi.mock("../api/reportFiles", () => ({
  uploadPairReportFile: vi.fn(),
  uploadPatientReportFile: vi.fn(),
}))
// DonorForm fetches this internally unless hideIntendedRecipientPicker is
// passed -- NewPairPage always passes it, so this should never actually be
// called, but the module still needs a mock to avoid a real network call
// if that ever regresses.
vi.mock("../api/patients", () => ({ listPatients: vi.fn().mockResolvedValue([]) }))

function renderPage() {
  return render(
    <BackgroundJobsProvider>
      <MemoryRouter initialEntries={["/pairs/new"]}>
        <Routes>
          <Route path="/pairs/new" element={<NewPairPage />} />
          <Route path="/patients/:patientId" element={<div>Patient Detail</div>} />
        </Routes>
      </MemoryRouter>
    </BackgroundJobsProvider>
  )
}

async function fillRequiredFields(user, sectionHeading, { bloodType, rh }) {
  const section = screen.getByRole("heading", { name: sectionHeading }).closest("div")
  await user.type(within(section).getByLabelText("Full name", { exact: false }), `${sectionHeading} Person`)
  await user.type(within(section).getByLabelText("Date of birth", { exact: false }), "1990-01-01")
  await user.click(within(section).getByRole("radio", { name: bloodType }))
  await user.click(within(section).getByRole("radio", { name: rh }))
}

async function saveSection(user, sectionHeading, saveLabel) {
  const section = screen.getByRole("heading", { name: sectionHeading }).closest("div")
  await user.click(within(section).getByRole("button", { name: saveLabel }))
}

async function fillAndSaveBothForms(user) {
  await fillRequiredFields(user, "Patient", { bloodType: "O", rh: "Positive (+)" })
  await saveSection(user, "Patient", "Save patient details")
  await fillRequiredFields(user, "Donor", { bloodType: "O", rh: "Positive (+)" })
  await saveSection(user, "Donor", "Save donor details")
}

describe("NewPairPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("only ever extracts the two joint documents, never the bead specificity slots", async () => {
    const user = userEvent.setup()
    startExtractionJob.mockResolvedValue({ job_id: "job-1" })
    getExtractionJob.mockResolvedValue({ job_id: "job-1", status: "running", documents: {} })

    renderPage()

    await user.upload(
      screen.getByLabelText("Histocompatibility Type-match Report"),
      new File(["x"], "typing.pdf", { type: "application/pdf" })
    )
    await user.upload(
      screen.getByLabelText("Bead Specificity Chart — Page 1"),
      new File(["x"], "bead1.pdf", { type: "application/pdf" })
    )
    await user.click(screen.getByRole("button", { name: "Extract details" }))

    await waitFor(() => expect(startExtractionJob).toHaveBeenCalled())
    const sentPhotos = startExtractionJob.mock.calls[0][0]
    expect(sentPhotos.hlaTypingReport).toBeInstanceOf(File)
    expect(sentPhotos.beadSpecificityPage1).toBeUndefined()
    expect(sentPhotos.beadSpecificityPage2).toBeUndefined()
  })

  it("explains why Register is disabled before either sub-form has been saved", async () => {
    renderPage()

    const registerButton = screen.getByRole("button", { name: /register patient/i })
    expect(registerButton).toBeDisabled()
    expect(
      screen.getByText('Click "Save patient details" and "Save donor details" above before registering.')
    ).toBeInTheDocument()
  })

  it("narrows the disabled-Register hint down to whichever sub-form is still unsaved", async () => {
    const user = userEvent.setup()
    renderPage()

    await fillRequiredFields(user, "Patient", { bloodType: "O", rh: "Positive (+)" })
    await saveSection(user, "Patient", "Save patient details")

    expect(screen.getByText('Click "Save donor details" above before registering.')).toBeInTheDocument()
  })

  it("blocks Register while an OCR-populated group is unconfirmed, then allows it once confirmed", async () => {
    const user = userEvent.setup()
    startExtractionJob.mockResolvedValue({ job_id: "job-1" })
    getExtractionJob.mockResolvedValue({
      job_id: "job-1",
      status: "done",
      documents: {
        hla_typing_report: {
          status: "done",
          completed: 1,
          total: 1,
          patient_details: {},
          donor_details: {},
          patient_hla: [{ locus: "A", allele_1: "01", allele_2: "02" }],
          donor_hla: [],
          bead_specificity: [],
          crossmatch: {},
          errors: [],
        },
      },
    })

    renderPage()
    await user.upload(
      screen.getByLabelText("Histocompatibility Type-match Report"),
      new File(["x"], "typing.pdf", { type: "application/pdf" })
    )
    await user.click(screen.getByRole("button", { name: "Extract details" }))
    await screen.findByText(/reviewed the HLA typing/)

    await fillAndSaveBothForms(user)

    const registerButton = screen.getByRole("button", { name: /register patient/i })
    expect(registerButton).toBeDisabled()

    await user.click(screen.getByRole("switch", { name: /reviewed the HLA typing/ }))
    expect(registerButton).toBeEnabled()
  })

  it("does not re-register the pair on retry after a failed file upload", async () => {
    const user = userEvent.setup()
    createPair.mockResolvedValue({ id: "pair-1", patient_id: "patient-1", donor_id: "donor-1" })
    uploadPairReportFile.mockRejectedValueOnce(new Error("network down"))

    renderPage()
    await user.upload(
      screen.getByLabelText("Histocompatibility Type-match Report"),
      new File(["x"], "typing.pdf", { type: "application/pdf" })
    )
    await fillAndSaveBothForms(user)

    await user.click(screen.getByRole("button", { name: /register patient/i }))
    await screen.findByText(/network down/)
    expect(createPair).toHaveBeenCalledTimes(1)

    uploadPairReportFile.mockResolvedValueOnce({ id: "file-1" })
    await user.click(screen.getByRole("button", { name: /register patient/i }))

    await waitFor(() => expect(screen.getByText("Patient Detail")).toBeInTheDocument())
    // Retry resumed from progress instead of re-registering the patient/donor.
    expect(createPair).toHaveBeenCalledTimes(1)
    expect(uploadPairReportFile).toHaveBeenCalledTimes(2)
  })

  it("kicks off a background bead-specificity extraction job after registering, without blocking navigation", async () => {
    // Restored after being deleted entirely (implementation-prompt-part-
    // j.md J0-J3) and then reinstated with a backend-side guard against
    // overwriting an existing profile (see ocr_job_service.py's
    // _save_bead_specificity_if_present) -- this test only covers the
    // frontend's half: the job still gets started and tracked.
    const user = userEvent.setup()
    createPair.mockResolvedValue({ id: "pair-1", patient_id: "patient-1", donor_id: "donor-1" })
    uploadPatientReportFile.mockResolvedValue({ id: "file-1" })
    startExtractionJob.mockResolvedValue({ job_id: "bead-job-1" })

    renderPage()
    await user.upload(
      screen.getByLabelText("Bead Specificity Chart — Page 1"),
      new File(["x"], "bead1.pdf", { type: "application/pdf" })
    )
    await fillAndSaveBothForms(user)

    await user.click(screen.getByRole("button", { name: /register patient/i }))

    await waitFor(() => expect(screen.getByText("Patient Detail")).toBeInTheDocument())
    expect(startExtractionJob).toHaveBeenCalledWith(
      expect.objectContaining({ beadSpecificityPage1: expect.any(File) }),
      "patient-1"
    )
  })

  it("still navigates to the patient page if starting the background bead-specificity job fails", async () => {
    const user = userEvent.setup()
    createPair.mockResolvedValue({ id: "pair-1", patient_id: "patient-1", donor_id: "donor-1" })
    uploadPatientReportFile.mockResolvedValue({ id: "file-1" })
    startExtractionJob.mockRejectedValue(new Error("network down"))

    renderPage()
    await user.upload(
      screen.getByLabelText("Bead Specificity Chart — Page 1"),
      new File(["x"], "bead1.pdf", { type: "application/pdf" })
    )
    await fillAndSaveBothForms(user)

    await user.click(screen.getByRole("button", { name: /register patient/i }))

    await waitFor(() => expect(screen.getByText("Patient Detail")).toBeInTheDocument())
  })
})

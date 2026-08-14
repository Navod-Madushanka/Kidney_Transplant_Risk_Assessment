// src/pages/NewCheckFromRecordsPage.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { listPatients, getPatientHlaTypings, getPatientAntibodyProfiles } from "../api/patients"
import { listDonors, getDonorHlaTypings } from "../api/donors"
import { listPairs } from "../api/pairs"
import {
  listPatientReportFiles,
  listPairReportFiles,
  fetchPatientReportFileBlob,
  fetchPairReportFileBlob,
} from "../api/reportFiles"
import NewCheckFromRecordsPage from "./NewCheckFromRecordsPage"

vi.mock("../api/patients", () => ({
  listPatients: vi.fn(),
  getPatientHlaTypings: vi.fn(),
  getPatientAntibodyProfiles: vi.fn(),
}))
vi.mock("../api/donors", () => ({ listDonors: vi.fn(), getDonorHlaTypings: vi.fn() }))
vi.mock("../api/pairs", () => ({ listPairs: vi.fn() }))
vi.mock("../api/reportFiles", () => ({
  listPatientReportFiles: vi.fn(),
  listPairReportFiles: vi.fn(),
  fetchPatientReportFileBlob: vi.fn(),
  fetchPairReportFileBlob: vi.fn(),
}))

const PATIENT = { id: "patient-1", full_name: "Alice Patient", nic_number: "199012345678" }
const DONOR = { id: "donor-1", full_name: "Bob Donor", nic_number: "198512345678" }
const PAIR = { id: "pair-1", patient_id: "patient-1", donor_id: "donor-1" }

const HLA_FILE = {
  id: "file-hla",
  category: "hla_typing_report",
  original_filename: "typing.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  created_at: "2026-08-01T00:00:00Z",
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/checks/start-from-records"]}>
      <Routes>
        <Route path="/checks/start-from-records" element={<NewCheckFromRecordsPage />} />
        <Route path="/checks/new/subject" element={<div>Subject Step</div>} />
      </Routes>
    </MemoryRouter>
  )
}

async function pickPatientAndDonor(user) {
  await user.selectOptions(await screen.findByLabelText("Patient"), "patient-1")
  await user.selectOptions(screen.getByLabelText("Donor"), "donor-1")
}

describe("NewCheckFromRecordsPage", () => {
  beforeEach(() => {
    getPatientHlaTypings.mockResolvedValue([])
    getDonorHlaTypings.mockResolvedValue([])
    getPatientAntibodyProfiles.mockResolvedValue([])
  })

  it("lists patients and donors to choose from", async () => {
    listPatients.mockResolvedValue([PATIENT])
    listDonors.mockResolvedValue([DONOR])

    renderPage()

    expect(await screen.findByText("Alice Patient — 199012345678")).toBeInTheDocument()
    expect(screen.getByText("Bob Donor — 198512345678")).toBeInTheDocument()
  })

  it("shows which wizard slots have an archived match once both are picked", async () => {
    const user = userEvent.setup()
    listPatients.mockResolvedValue([PATIENT])
    listDonors.mockResolvedValue([DONOR])
    listPairs.mockResolvedValue([PAIR])
    listPairReportFiles.mockResolvedValue([HLA_FILE])
    listPatientReportFiles.mockResolvedValue([])

    renderPage()
    await pickPatientAndDonor(user)

    expect(await screen.findByText(/Found in this pair's records — typing\.pdf/)).toBeInTheDocument()
    expect(screen.getByText("1 of 4 photo slots will be pre-filled")).toBeInTheDocument()
    // Crossmatch wasn't archived on the pair.
    const crossmatchRow = screen.getByText("Crossmatch Report").closest("li")
    expect(crossmatchRow).toHaveTextContent("Not archived — upload manually")
  })

  it("fetches the matched files, wraps them as Files, and navigates into the wizard's Photos step with them", async () => {
    const user = userEvent.setup()
    listPatients.mockResolvedValue([PATIENT])
    listDonors.mockResolvedValue([DONOR])
    listPairs.mockResolvedValue([PAIR])
    listPairReportFiles.mockResolvedValue([HLA_FILE])
    listPatientReportFiles.mockResolvedValue([])
    const blob = new Blob(["fake pdf bytes"], { type: "application/pdf" })
    fetchPairReportFileBlob.mockResolvedValue(blob)

    renderPage()
    await pickPatientAndDonor(user)
    await screen.findByText(/Found in this pair's records/)

    await user.click(screen.getByRole("button", { name: "Start compatibility check" }))

    await waitFor(() =>
      expect(fetchPairReportFileBlob).toHaveBeenCalledWith("pair-1", "file-hla")
    )
    expect(await screen.findByText("Subject Step")).toBeInTheDocument()
  })

  it("fetches each record's saved HLA typing before starting the check", async () => {
    const user = userEvent.setup()
    listPatients.mockResolvedValue([PATIENT])
    listDonors.mockResolvedValue([DONOR])
    listPairs.mockResolvedValue([])
    listPatientReportFiles.mockResolvedValue([])
    getPatientHlaTypings.mockResolvedValue([{ locus: "A", allele_1: "01:01", allele_2: "02:01" }])
    getDonorHlaTypings.mockResolvedValue([{ locus: "A", allele_1: "03:01", allele_2: "11:01" }])

    renderPage()
    await pickPatientAndDonor(user)
    await user.click(screen.getByRole("button", { name: "Start compatibility check" }))

    await waitFor(() => expect(getPatientHlaTypings).toHaveBeenCalledWith("patient-1"))
    expect(getDonorHlaTypings).toHaveBeenCalledWith("donor-1")
    expect(await screen.findByText("Subject Step")).toBeInTheDocument()
  })

  it("fetches the patient's saved antibody/bead-specificity profile before starting the check", async () => {
    const user = userEvent.setup()
    listPatients.mockResolvedValue([PATIENT])
    listDonors.mockResolvedValue([DONOR])
    listPairs.mockResolvedValue([])
    listPatientReportFiles.mockResolvedValue([])
    getPatientAntibodyProfiles.mockResolvedValue([{ antigen: "B7", mfi: 3500 }])

    renderPage()
    await pickPatientAndDonor(user)
    await user.click(screen.getByRole("button", { name: "Start compatibility check" }))

    await waitFor(() => expect(getPatientAntibodyProfiles).toHaveBeenCalledWith("patient-1"))
    expect(await screen.findByText("Subject Step")).toBeInTheDocument()
  })

  it("still starts the check if fetching the saved antibody profile fails", async () => {
    const user = userEvent.setup()
    listPatients.mockResolvedValue([PATIENT])
    listDonors.mockResolvedValue([DONOR])
    listPairs.mockResolvedValue([])
    listPatientReportFiles.mockResolvedValue([])
    getPatientAntibodyProfiles.mockRejectedValue(new Error("network down"))

    renderPage()
    await pickPatientAndDonor(user)
    await user.click(screen.getByRole("button", { name: "Start compatibility check" }))

    expect(await screen.findByText("Subject Step")).toBeInTheDocument()
  })

  it("still starts the check if fetching saved HLA typing fails", async () => {
    const user = userEvent.setup()
    listPatients.mockResolvedValue([PATIENT])
    listDonors.mockResolvedValue([DONOR])
    listPairs.mockResolvedValue([])
    listPatientReportFiles.mockResolvedValue([])
    getPatientHlaTypings.mockRejectedValue(new Error("network down"))

    renderPage()
    await pickPatientAndDonor(user)
    await user.click(screen.getByRole("button", { name: "Start compatibility check" }))

    expect(await screen.findByText("Subject Step")).toBeInTheDocument()
  })

  it("still lets the doctor start the check manually if the archive lookup fails", async () => {
    const user = userEvent.setup()
    listPatients.mockResolvedValue([PATIENT])
    listDonors.mockResolvedValue([DONOR])
    listPairs.mockResolvedValue([])
    listPatientReportFiles.mockRejectedValue(new Error("network down"))

    renderPage()
    await pickPatientAndDonor(user)

    expect(
      await screen.findByText(/Couldn't check archived report files for this pair/)
    ).toBeInTheDocument()
    const startButton = screen.getByRole("button", { name: "Start compatibility check" })
    expect(startButton).toBeEnabled()

    await user.click(startButton)
    expect(await screen.findByText("Subject Step")).toBeInTheDocument()
  })
})

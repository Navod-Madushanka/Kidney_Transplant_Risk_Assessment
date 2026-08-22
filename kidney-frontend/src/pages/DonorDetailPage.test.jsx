// src/pages/DonorDetailPage.test.jsx
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { getDonor, getDonorHlaTypings } from "../api/donors"
import { getPatient } from "../api/patients"
import { listPairs } from "../api/pairs"
import DonorDetailPage from "./DonorDetailPage"

vi.mock("../api/donors", () => ({
  getDonor: vi.fn(),
  updateDonor: vi.fn(),
  deleteDonor: vi.fn(),
  getDonorHlaTypings: vi.fn(),
  replaceDonorHlaTypings: vi.fn(),
  updateDonorStatus: vi.fn(),
}))
vi.mock("../api/patients", () => ({ getPatient: vi.fn() }))
vi.mock("../api/pairs", () => ({ listPairs: vi.fn() }))
vi.mock("../api/reportFiles", () => ({
  listPairReportFiles: vi.fn(),
  downloadPairReportFile: vi.fn(),
}))

const DONOR = {
  id: "donor-1",
  full_name: "Bob Donor",
  date_of_birth: "1990-02-20",
  blood_type: "O",
  rh_factor: "+",
  nic_number: "200000000007",
  status: "available",
  intended_recipient_id: null,
  egfr: null,
  systolic_bp: null,
  diastolic_bp: null,
  bmi: null,
  has_diabetes: null,
  sex: null,
  race: null,
  smoking_status: null,
  creatinine: null,
  urine_acr: null,
  is_on_antihypertensive_medication: null,
  family_history_kidney_disease: null,
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/donors/donor-1"]}>
      <Routes>
        <Route path="/donors/:donorId" element={<DonorDetailPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe("DonorDetailPage", () => {
  it("renders no upload control anywhere -- donors own no documents", async () => {
    getDonor.mockResolvedValue(DONOR)
    getDonorHlaTypings.mockResolvedValue([])
    listPairs.mockResolvedValue([])
    getPatient.mockResolvedValue(null)

    renderPage()

    expect(await screen.findByText("Bob Donor")).toBeInTheDocument()
    // The old <ReportFilesCard> upload flow is gone from this page entirely
    // -- PairDocumentsCard is read-only (download only).
    expect(document.querySelector('input[type="file"]')).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /upload/i })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /replace/i })).not.toBeInTheDocument()
    expect(await screen.findByText(/Not registered as a pair yet/)).toBeInTheDocument()
  })
})

// src/pages/DonorSearchPage.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { getPatient } from "../api/patients"
import { searchCompatibleDonors } from "../api/donorSearch"
import { runCompatibilityCheck } from "../api/compatibility"
import DonorSearchPage from "./DonorSearchPage"

vi.mock("../api/patients", () => ({ getPatient: vi.fn() }))
vi.mock("../api/donorSearch", () => ({ searchCompatibleDonors: vi.fn() }))
vi.mock("../api/compatibility", () => ({ runCompatibilityCheck: vi.fn() }))

const CANDIDATE = {
  donor_id: "donor-1",
  hospital_name: "Second Test Hospital",
  doctor_full_name: "Dr. Second Doctor",
  doctor_email: "second@example.com",
  blood_type: "O",
  rh_factor: "+",
  status: "available",
  abo_result: { is_compatible: true },
  mismatch_result: { total_mismatches: 2, bucket_name: "<3 mismatches", is_halted: false },
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/patients/patient-1/donor-search"]}>
      <Routes>
        <Route path="/patients/:patientId/donor-search" element={<DonorSearchPage />} />
        <Route path="/reports/:reportId" element={<div>Report Detail Page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe("DonorSearchPage", () => {
  it("renders the ranked candidate list once the search resolves", async () => {
    getPatient.mockResolvedValue({ id: "patient-1", full_name: "Alice Patient" })
    searchCompatibleDonors.mockResolvedValue([CANDIDATE])

    renderPage()

    expect(await screen.findByText("Second Test Hospital")).toBeInTheDocument()
    expect(screen.getByText("Dr. Second Doctor")).toBeInTheDocument()
    expect(screen.getByText("second@example.com")).toBeInTheDocument()
    expect(screen.getByText("2 (1-2 mismatches)")).toBeInTheDocument()
  })

  it("shows an empty-state message when no candidates come back", async () => {
    getPatient.mockResolvedValue({ id: "patient-1", full_name: "Alice Patient" })
    searchCompatibleDonors.mockResolvedValue([])

    renderPage()

    expect(
      await screen.findByText("No compatible donors found in the wider pool right now.")
    ).toBeInTheDocument()
  })

  it("shows an error-state message when the search fails", async () => {
    getPatient.mockResolvedValue({ id: "patient-1", full_name: "Alice Patient" })
    searchCompatibleDonors.mockRejectedValue(new Error("network down"))

    renderPage()

    expect(
      await screen.findByText("Couldn't load candidate donors. Please try refreshing.")
    ).toBeInTheDocument()
  })

  it("runs the compatibility check against the selected donor and navigates to the new report", async () => {
    const user = userEvent.setup()
    getPatient.mockResolvedValue({ id: "patient-1", full_name: "Alice Patient" })
    searchCompatibleDonors.mockResolvedValue([CANDIDATE])
    runCompatibilityCheck.mockResolvedValue({ id: "report-1" })

    renderPage()

    await user.click(await screen.findByRole("button", { name: /run compatibility check/i }))

    await waitFor(() =>
      expect(runCompatibilityCheck).toHaveBeenCalledWith("patient-1", "donor-1")
    )
    expect(await screen.findByText("Report Detail Page")).toBeInTheDocument()
  })
})

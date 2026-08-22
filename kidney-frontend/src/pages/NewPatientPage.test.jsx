// src/pages/NewPatientPage.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { createPatient } from "../api/patients"
import NewPatientPage from "./NewPatientPage"

vi.mock("../api/patients", () => ({ createPatient: vi.fn() }))

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/patients/new"]}>
      <Routes>
        <Route path="/patients/new" element={<NewPatientPage />} />
        <Route path="/patients/:patientId" element={<div>Patient Detail</div>} />
      </Routes>
    </MemoryRouter>
  )
}

async function fillRequiredFields(user) {
  await user.type(screen.getByLabelText("Full name", { exact: false }), "New Patient")
  await user.type(screen.getByLabelText("Date of birth", { exact: false }), "1990-01-01")
  await user.click(screen.getByRole("radio", { name: "O" }))
  await user.click(screen.getByRole("radio", { name: "Positive (+)" }))
}

describe("NewPatientPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("navigates to the new patient's page on success", async () => {
    const user = userEvent.setup()
    createPatient.mockResolvedValue({ id: "patient-1" })

    renderPage()
    await fillRequiredFields(user)
    await user.click(screen.getByRole("button", { name: "Add patient" }))

    await waitFor(() => expect(screen.getByText("Patient Detail")).toBeInTheDocument())
  })

  it("surfaces a duplicate-NIC failure instead of failing silently", async () => {
    // Regression: handleSubmit used to be try {} finally {} with no catch --
    // the button stopped spinning on a rejected createPatient() call with no
    // other sign anything had gone wrong.
    const user = userEvent.setup()
    createPatient.mockRejectedValue(new Error("A patient with this NIC already exists"))

    renderPage()
    await fillRequiredFields(user)
    const submitButton = screen.getByRole("button", { name: "Add patient" })
    await user.click(submitButton)

    await screen.findByText("A patient with this NIC already exists")
    // Only one copy of the message -- not also duplicated via PatientForm's
    // own internal formError, which would fire if handleSubmit still
    // re-threw after catching.
    expect(screen.getAllByText("A patient with this NIC already exists")).toHaveLength(1)
    expect(submitButton).toBeEnabled()
    expect(screen.queryByText("Patient Detail")).not.toBeInTheDocument()
  })
})

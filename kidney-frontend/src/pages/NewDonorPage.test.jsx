// src/pages/NewDonorPage.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { createDonor } from "../api/donors"
import NewDonorPage from "./NewDonorPage"

vi.mock("../api/donors", () => ({ createDonor: vi.fn() }))
// DonorForm fetches this internally for the intended-recipient picker.
vi.mock("../api/patients", () => ({ listPatients: vi.fn().mockResolvedValue([]) }))

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/donors/new"]}>
      <Routes>
        <Route path="/donors/new" element={<NewDonorPage />} />
        <Route path="/donors/:donorId" element={<div>Donor Detail</div>} />
      </Routes>
    </MemoryRouter>
  )
}

async function fillRequiredFields(user) {
  await user.type(screen.getByLabelText("Full name", { exact: false }), "New Donor")
  await user.type(screen.getByLabelText("Date of birth", { exact: false }), "1985-01-01")
  await user.click(screen.getByRole("radio", { name: "O" }))
  await user.click(screen.getByRole("radio", { name: "Positive (+)" }))
}

describe("NewDonorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("navigates to the new donor's page on success", async () => {
    const user = userEvent.setup()
    createDonor.mockResolvedValue({ id: "donor-1" })

    renderPage()
    await fillRequiredFields(user)
    await user.click(screen.getByRole("button", { name: "Add donor" }))

    await waitFor(() => expect(screen.getByText("Donor Detail")).toBeInTheDocument())
  })

  it("surfaces a duplicate-NIC failure instead of failing silently", async () => {
    // Regression: handleSubmit used to be try {} finally {} with no catch --
    // the button stopped spinning on a rejected createDonor() call with no
    // other sign anything had gone wrong.
    const user = userEvent.setup()
    createDonor.mockRejectedValue(new Error("A donor with this NIC already exists"))

    renderPage()
    await fillRequiredFields(user)
    const submitButton = screen.getByRole("button", { name: "Add donor" })
    await user.click(submitButton)

    await screen.findByText("A donor with this NIC already exists")
    // Only one copy of the message -- not also duplicated via DonorForm's
    // own internal formError, which would fire if handleSubmit still
    // re-threw after catching.
    expect(screen.getAllByText("A donor with this NIC already exists")).toHaveLength(1)
    expect(submitButton).toBeEnabled()
    expect(screen.queryByText("Donor Detail")).not.toBeInTheDocument()
  })
})

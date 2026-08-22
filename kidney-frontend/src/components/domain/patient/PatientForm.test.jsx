// src/components/domain/patient/PatientForm.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import PatientForm from "./PatientForm"

const EXISTING_PATIENT = {
  fullName: "Alice Patient",
  dateOfBirth: "1985-06-15",
  bloodType: "AB",
  rhFactor: "+",
  nicNumber: "200000000008",
}

describe("PatientForm", () => {
  it("create mode requires blood group and RhD type", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<PatientForm onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText("Full name", { exact: false }), "New Patient")
    await user.type(screen.getByLabelText("Date of birth", { exact: false }), "1990-01-01")
    await user.click(screen.getByRole("button", { name: "Save patient" }))

    expect(screen.getByText("Blood group is required")).toBeInTheDocument()
    expect(screen.getByText("RhD type is required")).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("create mode submits blood_type/rh_factor as part of the payload", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<PatientForm onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText("Full name", { exact: false }), "New Patient")
    await user.type(screen.getByLabelText("Date of birth", { exact: false }), "1990-01-01")
    await user.click(screen.getByRole("radio", { name: "O" }))
    await user.click(screen.getByRole("radio", { name: "Positive (+)" }))
    await user.click(screen.getByRole("button", { name: "Save patient" }))

    expect(onSubmit).toHaveBeenCalledWith({
      full_name: "New Patient",
      date_of_birth: "1990-01-01",
      nic_number: null,
      blood_type: "O",
      rh_factor: "+",
      sex: null,
      weight_kg: null,
      dialysis_start_date: null,
    })
  })

  it("edit mode locks blood group and RhD type controls", () => {
    render(<PatientForm mode="edit" initialValues={EXISTING_PATIENT} onSubmit={vi.fn()} />)

    expect(screen.getByRole("radio", { name: "AB" })).toBeDisabled()
    expect(screen.getByRole("radio", { name: "Positive (+)" })).toBeDisabled()
    expect(screen.getAllByText("Locked after creation")).toHaveLength(2)
  })

  it("edit mode does not require blood group/RhD type and omits them from the payload", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <PatientForm
        mode="edit"
        submitLabel="Save changes"
        initialValues={EXISTING_PATIENT}
        onSubmit={onSubmit}
      />
    )

    await user.clear(screen.getByLabelText("Full name", { exact: false }))
    await user.type(screen.getByLabelText("Full name", { exact: false }), "Alice Renamed")
    await user.click(screen.getByRole("button", { name: "Save changes" }))

    expect(onSubmit).toHaveBeenCalledWith({
      full_name: "Alice Renamed",
      date_of_birth: "1985-06-15",
      nic_number: "200000000008",
      sex: null,
      weight_kg: null,
      dialysis_start_date: null,
    })
  })

  it("edit mode still requires full name and date of birth", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <PatientForm
        mode="edit"
        submitLabel="Save changes"
        initialValues={EXISTING_PATIENT}
        onSubmit={onSubmit}
      />
    )

    await user.clear(screen.getByLabelText("Full name", { exact: false }))
    await user.click(screen.getByRole("button", { name: "Save changes" }))

    expect(screen.getByText("Full name is required")).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })
})

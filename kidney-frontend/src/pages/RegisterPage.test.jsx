// src/pages/RegisterPage.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { AuthContext } from "../context/AuthContext"
import { ApiError } from "../api/client"
import RegisterPage from "./RegisterPage"

function renderRegisterPage(authValue) {
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={["/register"]}>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  )
}

async function fillValidForm(user) {
  await user.type(screen.getByLabelText(/your full name/i), "Dr. Jane Doe")
  await user.type(screen.getByLabelText(/^email/i), "jane@example.com")
  await user.type(screen.getByLabelText(/^password/i), "supersecret123")
  await user.type(screen.getByLabelText(/confirm password/i), "supersecret123")
}

describe("RegisterPage", () => {
  it("requires full name, email, and password before calling register", async () => {
    const user = userEvent.setup()
    const register = vi.fn()
    renderRegisterPage({ register })

    await user.click(screen.getByRole("button", { name: /create account/i }))

    expect(await screen.findByText("Your full name is required")).toBeInTheDocument()
    expect(screen.getByText("Email is required")).toBeInTheDocument()
    expect(screen.getByText("Password is required")).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })

  it("rejects a password shorter than 8 characters", async () => {
    const user = userEvent.setup()
    const register = vi.fn()
    renderRegisterPage({ register })

    await user.type(screen.getByLabelText(/your full name/i), "Dr. Jane Doe")
    await user.type(screen.getByLabelText(/^email/i), "jane@example.com")
    await user.type(screen.getByLabelText(/^password/i), "short")
    await user.type(screen.getByLabelText(/confirm password/i), "short")
    await user.click(screen.getByRole("button", { name: /create account/i }))

    expect(
      await screen.findByText("Password must be at least 8 characters")
    ).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })

  it("rejects mismatched password confirmation", async () => {
    const user = userEvent.setup()
    const register = vi.fn()
    renderRegisterPage({ register })

    await user.type(screen.getByLabelText(/your full name/i), "Dr. Jane Doe")
    await user.type(screen.getByLabelText(/^email/i), "jane@example.com")
    await user.type(screen.getByLabelText(/^password/i), "supersecret123")
    await user.type(screen.getByLabelText(/confirm password/i), "does-not-match")
    await user.click(screen.getByRole("button", { name: /create account/i }))

    expect(await screen.findByText("Passwords don't match")).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })

  it("submits a hardcoded hospital name alongside the doctor's details", async () => {
    const user = userEvent.setup()
    const register = vi.fn().mockResolvedValue(undefined)
    renderRegisterPage({ register })

    await fillValidForm(user)
    await user.click(screen.getByRole("button", { name: /create account/i }))

    await waitFor(() =>
      expect(register).toHaveBeenCalledWith({
        email: "jane@example.com",
        password: "supersecret123",
        fullName: "Dr. Jane Doe",
        hospitalName: "Kandy National Hospital Sri Lanka",
      })
    )
    expect(await screen.findByText("Login Page")).toBeInTheDocument()
  })

  it("shows the existing-account message on a 400 response", async () => {
    const user = userEvent.setup()
    const register = vi
      .fn()
      .mockRejectedValue(new ApiError("An account with this email already exists", 400, null))
    renderRegisterPage({ register })

    await fillValidForm(user)
    await user.click(screen.getByRole("button", { name: /create account/i }))

    expect(
      await screen.findByText("An account with this email already exists")
    ).toBeInTheDocument()
  })
})

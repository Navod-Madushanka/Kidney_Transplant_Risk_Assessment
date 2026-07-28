// src/pages/LoginPage.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { AuthContext } from "../context/AuthContext"
import { ApiError } from "../api/client"
import LoginPage from "./LoginPage"

function renderLoginPage(authValue) {
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Dashboard Home</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  )
}

describe("LoginPage", () => {
  it("shows validation errors instead of calling login when fields are empty", async () => {
    const user = userEvent.setup()
    const login = vi.fn()
    renderLoginPage({ login })

    await user.click(screen.getByRole("button", { name: /log in/i }))

    expect(await screen.findByText("Email is required")).toBeInTheDocument()
    expect(screen.getByText("Password is required")).toBeInTheDocument()
    expect(login).not.toHaveBeenCalled()
  })

  it("calls login with trimmed email and password, then navigates home on success", async () => {
    const user = userEvent.setup()
    const login = vi.fn().mockResolvedValue(undefined)
    renderLoginPage({ login })

    await user.type(screen.getByLabelText(/email/i), "  doctor@example.com  ")
    await user.type(screen.getByLabelText(/password/i), "correct-password")
    await user.click(screen.getByRole("button", { name: /log in/i }))

    await waitFor(() => expect(login).toHaveBeenCalledWith("doctor@example.com", "correct-password"))
    expect(await screen.findByText("Dashboard Home")).toBeInTheDocument()
  })

  it("shows a specific message when the API rejects with a 401", async () => {
    const user = userEvent.setup()
    const login = vi.fn().mockRejectedValue(new ApiError("Unauthorized", 401, null))
    renderLoginPage({ login })

    await user.type(screen.getByLabelText(/email/i), "doctor@example.com")
    await user.type(screen.getByLabelText(/password/i), "wrong-password")
    await user.click(screen.getByRole("button", { name: /log in/i }))

    expect(await screen.findByText("Incorrect email or password.")).toBeInTheDocument()
  })

  it("shows a generic message for non-401 failures", async () => {
    const user = userEvent.setup()
    const login = vi.fn().mockRejectedValue(new Error("network down"))
    renderLoginPage({ login })

    await user.type(screen.getByLabelText(/email/i), "doctor@example.com")
    await user.type(screen.getByLabelText(/password/i), "some-password")
    await user.click(screen.getByRole("button", { name: /log in/i }))

    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument()
  })
})

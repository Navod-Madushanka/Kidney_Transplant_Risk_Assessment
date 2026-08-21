// src/pages/RegisterPage.test.jsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it } from "vitest"
import RegisterPage from "./RegisterPage"

function renderRegisterPage() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe("RegisterPage", () => {
  it("shows a self-registration-disabled message instead of a signup form", () => {
    renderRegisterPage()

    expect(screen.getByText("Self-registration is disabled")).toBeInTheDocument()
    expect(
      screen.getByText("Contact your system administrator to request an account.")
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /create account/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  })

  it("links back to the login page", async () => {
    const user = userEvent.setup()
    renderRegisterPage()

    await user.click(screen.getByRole("link", { name: /log in/i }))

    expect(await screen.findByText("Login Page")).toBeInTheDocument()
  })
})

// src/layout/Sidebar.test.jsx
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import Sidebar from "./Sidebar"

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ user: { full_name: "Dr Test", role: "doctor" }, logout: vi.fn() }),
}))

describe("Sidebar", () => {
  it("shows the pending-decisions count on the Exchange item, and hides it at zero", () => {
    const { rerender } = render(
      <MemoryRouter>
        <Sidebar pendingExchangeCount={0} />
      </MemoryRouter>
    )
    expect(screen.queryByText("5")).not.toBeInTheDocument()

    rerender(
      <MemoryRouter>
        <Sidebar pendingExchangeCount={5} />
      </MemoryRouter>
    )
    expect(screen.getByText("5")).toBeInTheDocument()
  })
})

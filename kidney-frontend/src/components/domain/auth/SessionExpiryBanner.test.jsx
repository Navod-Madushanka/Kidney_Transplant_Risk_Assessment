// src/components/domain/auth/SessionExpiryBanner.test.jsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import SessionExpiryBanner from "./SessionExpiryBanner"
import { ApiError } from "../../../api/client"

const mockLogin = vi.fn()
const mockLogout = vi.fn()
let mockAuthState

// Mirrors SessionExpiryBanner.jsx's own WARNING_LEAD_MS (not exported --
// this test only needs it to construct scenarios just inside/outside the
// window, not to assert on it directly).
const WARNING_LEAD_MS = 5 * 60 * 1000

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => mockAuthState,
}))

function authenticatedState(msUntilExpiry) {
  return {
    status: "authenticated",
    user: { email: "doctor@example.com" },
    expiresAt: Date.now() + msUntilExpiry,
    login: mockLogin,
    logout: mockLogout,
  }
}

describe("SessionExpiryBanner", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockLogin.mockReset()
    mockLogout.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("renders nothing when the session has more than 5 minutes left", () => {
    mockAuthState = authenticatedState(10 * 60 * 1000)
    render(<SessionExpiryBanner />)

    expect(screen.queryByText(/session is about to expire/i)).not.toBeInTheDocument()
  })

  it("shows the warning once within 5 minutes of expiry", async () => {
    vi.useRealTimers()
    // Just outside the warning window at mount (so the initial synchronous
    // check stays false) and only 50ms from crossing it -- a real, short
    // wait rather than simulating a full ~5 minutes.
    mockAuthState = authenticatedState(WARNING_LEAD_MS + 50)
    render(<SessionExpiryBanner />)

    expect(screen.queryByText(/session is about to expire/i)).not.toBeInTheDocument()

    await waitFor(() =>
      expect(screen.getByText(/session is about to expire/i)).toBeInTheDocument()
    )
  })

  it("shows the warning immediately if already inside the warning window on mount", () => {
    mockAuthState = authenticatedState(2 * 60 * 1000)
    render(<SessionExpiryBanner />)

    expect(screen.getByText(/session is about to expire/i)).toBeInTheDocument()
  })

  it("signs the doctor out automatically at the real expiry instant", async () => {
    vi.useRealTimers()
    mockAuthState = authenticatedState(50)
    render(<SessionExpiryBanner />)

    await waitFor(() => expect(mockLogout).toHaveBeenCalled())
  })

  it("re-authenticating with the correct password dismisses the warning", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    mockLogin.mockResolvedValue(undefined)
    mockAuthState = authenticatedState(2 * 60 * 1000)
    render(<SessionExpiryBanner />)

    await user.type(screen.getByLabelText("Password", { exact: false }), "correct-password")
    await user.click(screen.getByRole("button", { name: "Stay signed in" }))

    expect(mockLogin).toHaveBeenCalledWith("doctor@example.com", "correct-password")
    await waitFor(() =>
      expect(screen.queryByText(/session is about to expire/i)).not.toBeInTheDocument()
    )
  })

  it("shows an inline error and stays open on the wrong password", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    mockLogin.mockRejectedValue(new ApiError("Incorrect email or password", 401))
    mockAuthState = authenticatedState(2 * 60 * 1000)
    render(<SessionExpiryBanner />)

    await user.type(screen.getByLabelText("Password", { exact: false }), "wrong-password")
    await user.click(screen.getByRole("button", { name: "Stay signed in" }))

    expect(await screen.findByText("Incorrect password.")).toBeInTheDocument()
    expect(screen.getByText(/session is about to expire/i)).toBeInTheDocument()
  })

  it("signs out immediately when the doctor chooses Sign out instead", async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    mockAuthState = authenticatedState(2 * 60 * 1000)
    render(<SessionExpiryBanner />)

    await user.click(screen.getByRole("button", { name: "Sign out" }))

    expect(mockLogout).toHaveBeenCalled()
  })
})

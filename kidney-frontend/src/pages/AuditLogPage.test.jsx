// src/pages/AuditLogPage.test.jsx
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { listAuditLogs, verifyAuditChain } from "../api/auditLogs"
import { ApiError } from "../api/client"
import AuditLogPage from "./AuditLogPage"

vi.mock("../api/auditLogs", () => ({
  listAuditLogs: vi.fn(),
  verifyAuditChain: vi.fn(),
}))

const SAMPLE_ROW = {
  id: "11111111-1111-1111-1111-111111111111",
  seq: 3,
  doctor_id: "22222222-2222-2222-2222-222222222222",
  action: "ran_compatibility_check",
  patient_id: "33333333-3333-3333-3333-333333333333",
  donor_id: "44444444-4444-4444-4444-444444444444",
  details: { overall_status: "pass" },
  created_at: "2026-08-09T10:00:00Z",
  prev_hash: "a".repeat(64),
  hash: "b".repeat(64),
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/audit-log"]}>
      <Routes>
        <Route path="/audit-log" element={<AuditLogPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe("AuditLogPage", () => {
  it("shows chain-intact status and the row list once both requests resolve", async () => {
    verifyAuditChain.mockResolvedValue({
      is_valid: true,
      checked_count: 3,
      total_count: 3,
      first_broken_id: null,
      reason: null,
    })
    listAuditLogs.mockResolvedValue({ rows: [SAMPLE_ROW], total_count: 1 })

    renderPage()

    expect(await screen.findByText("Chain intact")).toBeInTheDocument()
    expect(screen.getByText("ran_compatibility_check")).toBeInTheDocument()
  })

  it("shows chain-broken status with the reason", async () => {
    verifyAuditChain.mockResolvedValue({
      is_valid: false,
      checked_count: 1,
      total_count: 3,
      first_broken_id: SAMPLE_ROW.id,
      reason: "seq gap detected: expected seq 2, found 3",
    })
    listAuditLogs.mockResolvedValue({ rows: [], total_count: 0 })

    renderPage()

    expect(await screen.findByText("Chain broken")).toBeInTheDocument()
    expect(screen.getByText(/seq gap detected/)).toBeInTheDocument()
  })

  it("shows an admin-only message on a 403 instead of the generic error", async () => {
    verifyAuditChain.mockRejectedValue(new ApiError("Forbidden", 403, {}))
    listAuditLogs.mockRejectedValue(new ApiError("Forbidden", 403, {}))

    renderPage()

    expect(
      await screen.findByText("This page requires an administrator account.")
    ).toBeInTheDocument()
    expect(screen.queryByText("Couldn't load the audit log. Please try refreshing.")).not.toBeInTheDocument()
  })
})

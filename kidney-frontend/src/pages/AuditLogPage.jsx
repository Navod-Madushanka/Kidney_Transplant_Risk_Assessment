// src/pages/AuditLogPage.jsx
import { useEffect, useState } from "react"
import { listAuditLogs, verifyAuditChain } from "../api/auditLogs"
import { ApiError } from "../api/client"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import Table from "../components/ui/Table"

const PAGE_SIZE = 50

function formatTimestamp(isoString) {
  return new Date(isoString).toLocaleString()
}

// Short ids are still unique enough to scan/compare at a glance without
// wrapping every row onto three lines -- this is a raw system-of-record
// view for an admin, not a page anyone needs to copy full UUIDs out of by
// eye (the full value is still in the title attribute for anyone who does).
function shortId(id) {
  return id ? `${id.slice(0, 8)}…` : "—"
}

export default function AuditLogPage() {
  const [verifyState, setVerifyState] = useState({ status: "loading", result: null })
  const [listState, setListState] = useState({ status: "loading", rows: [], totalCount: 0 })
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    let cancelled = false
    verifyAuditChain()
      .then((result) => !cancelled && setVerifyState({ status: "loaded", result }))
      .catch((error) => !cancelled && setVerifyState({ status: "error", result: null, error }))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setListState((current) => ({ ...current, status: "loading" }))
    listAuditLogs(PAGE_SIZE, offset)
      .then(
        (data) =>
          !cancelled &&
          setListState({ status: "loaded", rows: data.rows, totalCount: data.total_count })
      )
      .catch((error) => !cancelled && setListState({ status: "error", rows: [], error }))
    return () => {
      cancelled = true
    }
  }, [offset])

  // Both requests 403 identically for a non-admin doctor who reaches this
  // page directly (the sidebar link itself is already admin-gated, but
  // gating a route only in the nav isn't real access control) -- treat
  // that as its own state rather than the generic "couldn't load" message,
  // since the fix here (log in as an admin) is different from "try
  // refreshing."
  const forbidden =
    (verifyState.error instanceof ApiError && verifyState.error.status === 403) ||
    (listState.error instanceof ApiError && listState.error.status === 403)

  if (forbidden) {
    return (
      <div className="border border-border rounded-lg p-8 text-center bg-surface max-w-2xl">
        <p className="text-[15px] text-text-muted">
          This page requires an administrator account.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 max-w-5xl">
      <div>
        <h1 className="text-[22px] font-bold text-text">Audit log</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Every recorded action, oldest first within each page, newest page first — tamper-evident
          via a hash chain (see the chain status below). Admin-only.
        </p>
      </div>

      <div className="border border-border rounded-lg bg-surface p-4 flex items-center gap-3">
        {verifyState.status === "loading" && (
          <>
            <div
              className="h-5 w-5 rounded-full border-2 border-border border-t-accent animate-spin"
              role="status"
              aria-label="Loading"
            />
            <span className="text-[14px] text-text-muted">Verifying chain integrity…</span>
          </>
        )}
        {verifyState.status === "error" && (
          <>
            <Badge status="neutral">Unknown</Badge>
            <span className="text-[14px] text-text-muted">Couldn't verify the chain. Please try refreshing.</span>
          </>
        )}
        {verifyState.status === "loaded" && verifyState.result.is_valid && (
          <>
            <Badge status="pass">Chain intact</Badge>
            <span className="text-[14px] text-text-muted">
              {verifyState.result.checked_count} of {verifyState.result.total_count} rows verified.
            </span>
          </>
        )}
        {verifyState.status === "loaded" && !verifyState.result.is_valid && (
          <>
            <Badge status="fail">Chain broken</Badge>
            <span className="text-[14px] text-text-muted">
              {verifyState.result.reason}
              {verifyState.result.first_broken_id && ` (row ${shortId(verifyState.result.first_broken_id)})`}
            </span>
          </>
        )}
      </div>

      {listState.status === "loading" && (
        <div className="flex justify-center py-16">
          <div
            className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin"
            role="status"
            aria-label="Loading"
          />
        </div>
      )}

      {listState.status === "error" && (
        <div className="border border-border rounded-lg p-8 text-center bg-surface">
          <p className="text-[15px] text-text-muted">Couldn't load the audit log. Please try refreshing.</p>
        </div>
      )}

      {listState.status === "loaded" && (
        <>
          <Table
            columns={[
              { key: "seq", label: "Seq", align: "right" },
              { key: "created_at", label: "When" },
              { key: "action", label: "Action" },
              { key: "doctor_id", label: "Doctor" },
              { key: "subject", label: "Patient / Donor" },
              { key: "details", label: "Details" },
            ]}
            rows={listState.rows}
            getRowId={(row) => row.id}
            emptyMessage="No audit entries recorded yet."
            renderCell={(row, col) => {
              switch (col.key) {
                case "seq":
                  return row.seq
                case "created_at":
                  return formatTimestamp(row.created_at)
                case "action":
                  return row.action
                case "doctor_id":
                  return <span title={row.doctor_id}>{shortId(row.doctor_id)}</span>
                case "subject":
                  return (
                    <span title={`patient: ${row.patient_id ?? "—"} / donor: ${row.donor_id ?? "—"}`}>
                      {row.patient_id ? `P ${shortId(row.patient_id)}` : ""}
                      {row.patient_id && row.donor_id ? " / " : ""}
                      {row.donor_id ? `D ${shortId(row.donor_id)}` : ""}
                      {!row.patient_id && !row.donor_id ? "—" : ""}
                    </span>
                  )
                case "details":
                  return (
                    <code className="text-[12px] text-text-muted break-all">
                      {row.details ? JSON.stringify(row.details) : "—"}
                    </code>
                  )
                default:
                  return null
              }
            }}
          />

          <div className="flex items-center justify-between text-[13px] text-text-muted">
            <span>
              {listState.totalCount === 0
                ? "0 entries"
                : `${offset + 1}–${Math.min(offset + PAGE_SIZE, listState.totalCount)} of ${listState.totalCount}`}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
              >
                Newer
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={offset + PAGE_SIZE >= listState.totalCount}
                onClick={() => setOffset((current) => current + PAGE_SIZE)}
              >
                Older
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

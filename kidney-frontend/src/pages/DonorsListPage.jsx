// src/pages/DonorsListPage.jsx
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { listDonors } from "../api/donors"
import Button from "../components/ui/Button"
import Badge from "../components/ui/Badge"
import { donorStatusBadgeProps } from "../constants/donorStatus"

function DonorRow({ donor }) {
  const { status: badgeStatus, label: badgeLabel } = donorStatusBadgeProps(donor.status)

  return (
    <Link
      to={`/donors/${donor.id}`}
      className="flex items-center justify-between gap-3 px-4 py-3.5 hover:bg-bg transition-colors"
    >
      <div className="min-w-0">
        <p className="text-[15px] font-semibold text-text truncate">{donor.full_name}</p>
        <p className="text-[13px] text-text-muted">
          {donor.nic_number || "No NIC on file"} · DOB {donor.date_of_birth}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Badge status="neutral">{donor.blood_type}</Badge>
        <Badge status={badgeStatus}>{badgeLabel}</Badge>
      </div>
    </Link>
  )
}

export default function DonorsListPage() {
  const [state, setState] = useState({ status: "loading", donors: [] })

  useEffect(() => {
    let cancelled = false
    listDonors()
      .then((donors) => !cancelled && setState({ status: "loaded", donors }))
      .catch(() => !cancelled && setState({ status: "error", donors: [] }))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-[22px] font-bold text-text">Donors</h1>
        {/* /pairs/new (via the sidebar) is the primary way to add people now
            -- most donors arrive with a patient already lined up. This stays
            for an altruistic/deceased donor with no intended recipient,
            which is what feeds cross-hospital search. */}
        <Link to="/donors/new">
          <Button variant="ghost" size="sm">
            Register individually
          </Button>
        </Link>
      </div>

      {state.status === "loading" && (
        <div className="flex justify-center py-16">
          <div
            className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin"
            role="status"
            aria-label="Loading"
          />
        </div>
      )}

      {state.status === "error" && (
        <div className="border border-border rounded-lg p-8 text-center bg-surface">
          <p className="text-[15px] text-text-muted">Couldn't load donors. Please try refreshing.</p>
        </div>
      )}

      {state.status === "loaded" && state.donors.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center bg-surface">
          <p className="text-[15px] text-text-muted">No donors yet.</p>
        </div>
      )}

      {state.status === "loaded" && state.donors.length > 0 && (
        <div className="bg-surface border border-border rounded-lg divide-y divide-border overflow-hidden">
          {state.donors.map((donor) => (
            <DonorRow key={donor.id} donor={donor} />
          ))}
        </div>
      )}
    </div>
  )
}
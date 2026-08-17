// src/pages/ExchangeProposalDetailPage.jsx
import { useCallback, useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"
import {
  cancelExchangeProposal,
  decideExchangeProposalPair,
  getExchangeProposal,
} from "../api/exchangeProposals"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import Card from "../components/ui/Card"
import EmptyState from "../components/ui/EmptyState"
import Spinner from "../components/ui/Spinner"

// See ExchangeProposalCard's docstring: workflow state, never the clinical
// palette.
const STATUS_LABELS = {
  proposed: "Pending",
  accepted: "Accepted — locked",
  declined: "Declined",
  expired: "Expired",
  cancelled: "Cancelled",
  completed: "Completed",
}

export default function ExchangeProposalDetailPage() {
  const { proposalId } = useParams()
  const { user } = useAuth()
  const [proposal, setProposal] = useState(null)
  const [failed, setFailed] = useState(false)
  const [isBusy, setBusy] = useState(false)
  const [declineReason, setDeclineReason] = useState("")

  const load = useCallback(() => {
    setFailed(false)
    return getExchangeProposal(proposalId)
      .then(setProposal)
      .catch(() => setFailed(true))
  }, [proposalId])

  useEffect(() => {
    load()
  }, [load])

  if (failed) {
    return <EmptyState message="Couldn't load this proposal. Please try refreshing." />
  }
  if (!proposal) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    )
  }

  const nodes = proposal.cycle_snapshot?.nodes ?? []
  const nodeByPairId = new Map(nodes.map((node) => [node.pair_id, node]))
  const pairRowByDonorId = new Map(proposal.pairs.map((pair) => [pair.donor_id, pair]))
  const myPendingPair = proposal.pairs.find(
    (pair) => pair.owning_doctor_id === user?.id && pair.decision === "pending"
  )
  const canDecide = Boolean(myPendingPair) && proposal.status === "proposed"
  const canCancel =
    proposal.created_by_doctor_id === user?.id && ["proposed", "accepted"].includes(proposal.status)

  async function handleDecision(decision) {
    setBusy(true)
    try {
      await decideExchangeProposalPair(
        proposalId,
        myPendingPair.id,
        decision,
        decision === "declined" ? declineReason || null : null
      )
      await load()
    } finally {
      setBusy(false)
    }
  }

  async function handleCancel() {
    setBusy(true)
    try {
      await cancelExchangeProposal(proposalId)
      await load()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 pb-4">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2 flex-wrap">
          <h1 className="text-[22px] font-bold text-text">Exchange proposal</h1>
          <Badge status="neutral">{STATUS_LABELS[proposal.status] ?? proposal.status}</Badge>
        </div>
        <p className="text-[14px] text-text-muted">
          {proposal.policy.replace(/_/g, " ")} · weight {proposal.weight.toFixed(1)} · expires{" "}
          {new Date(proposal.expires_at).toLocaleString()}
        </p>
      </div>

      <Card>
        <div className="flex flex-col">
          {nodes.map((node, index) => {
            const pairRow = pairRowByDonorId.get(node.pair_id)
            return (
              <div key={node.pair_id} className="flex flex-col">
                <div className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="text-[15px] font-semibold text-text">
                      {node.patient_blood_type}
                      <span className="text-text-muted font-normal"> recipient ← </span>
                      {node.donor_blood_type}
                      <span className="text-text-muted font-normal"> donor</span>
                    </p>
                    <p className="text-[13px] text-text-muted">
                      Donor: {node.donor_hospital_name} · {node.donor_doctor_full_name}
                    </p>
                    <p className="text-[13px] text-text-muted">
                      Recipient: {node.patient_hospital_name} · {node.patient_doctor_full_name}
                    </p>
                  </div>
                  <Badge status="neutral">{pairRow?.decision ?? "—"}</Badge>
                </div>
                {index < nodes.length - 1 ? (
                  <p className="text-[12px] text-text-muted pl-1">↓ gives to next pair's recipient</p>
                ) : (
                  <p className="text-[12px] text-accent pl-1">↺ closes back to the first pair</p>
                )}
              </div>
            )
          })}
        </div>
      </Card>

      {canCancel && (
        <div>
          <Button variant="secondary" size="sm" disabled={isBusy} onClick={handleCancel}>
            Cancel proposal
          </Button>
        </div>
      )}

      {/* Sticky action bar (K10): offset above TabBar's own height so it
          never overlaps it, with the safe-area inset folded into this
          bar's own bottom padding. Static (in-flow) at md+, where there's
          no TabBar to clear. */}
      {canDecide && (
        <div
          className="fixed bottom-16 left-0 right-0 z-40 bg-surface border-t border-border p-4 md:static md:border md:rounded-lg md:bottom-auto"
          style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}
        >
          <div className="max-w-6xl mx-auto flex flex-col sm:flex-row gap-2 sm:items-center sm:justify-between">
            <input
              type="text"
              value={declineReason}
              onChange={(event) => setDeclineReason(event.target.value)}
              placeholder="Decline reason (optional)"
              className="h-11 flex-1 rounded-md border border-border px-3.5 text-[15px] bg-surface text-text focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
            />
            <div className="flex gap-2 shrink-0">
              <Button variant="secondary" disabled={isBusy} onClick={() => handleDecision("declined")}>
                Decline
              </Button>
              <Button disabled={isBusy} onClick={() => handleDecision("accepted")}>
                Accept
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

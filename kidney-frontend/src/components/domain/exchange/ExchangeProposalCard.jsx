// src/components/domain/exchange/ExchangeProposalCard.jsx
import { useState } from "react"
import { Link } from "react-router-dom"
import Badge from "../../ui/Badge"
import Button from "../../ui/Button"
import Card from "../../ui/Card"
import Modal from "../../ui/Modal"

// K10: proposal workflow states are NOT clinical status -- every badge here
// uses Badge's "neutral" style (bg-bg/border, no clinical hue) even though
// this page sits right next to DSA/mismatch badges that DO use the clinical
// palette. See index.css's @theme comment: a color meaning something
// different in two places is the exact safety bug that rule exists to
// prevent.
const STATUS_LABELS = {
  proposed: "Pending",
  accepted: "Accepted — locked",
  declined: "Declined",
  expired: "Expired",
  cancelled: "Cancelled",
  completed: "Completed",
}

const DECISION_LABELS = {
  pending: "Awaiting decision",
  accepted: "Accepted",
  declined: "Declined",
}

/**
 * Usage:
 *   <ExchangeProposalCard
 *     proposal={proposal}
 *     currentDoctorId={user.id}
 *     detailLinkTo={`/exchange/proposals/${proposal.id}`}
 *     onAccept={(pair) => decide(proposal.id, pair, "accepted")}
 *     onDecline={(pair) => decide(proposal.id, pair, "declined")}
 *     onCancel={isProposer ? () => cancel(proposal.id) : null}
 *   />
 *
 * Renders one proposal as its cycle chain (same chain shape ExchangePoolPage
 * uses for a selected cycle), each pair showing its own decision state and,
 * for a pair the current doctor owns and still has pending, inline
 * accept/decline actions. `proposal.cycle_snapshot` is the frozen clinical
 * picture from proposal time (see exchange_proposal_service.build_cycle_
 * snapshot) -- its node order already matches the cycle's own order.
 */
export default function ExchangeProposalCard({
  proposal,
  currentDoctorId,
  onAccept,
  onDecline,
  onCancel,
  isBusy = false,
  detailLinkTo,
}) {
  const nodes = proposal.cycle_snapshot?.nodes ?? []
  const nodeByPairId = new Map(nodes.map((node) => [node.pair_id, node]))
  const pairRowByDonorId = new Map(proposal.pairs.map((pair) => [pair.donor_id, pair]))

  const canCancel = Boolean(onCancel) && ["proposed", "accepted"].includes(proposal.status)

  // Gates the actual onAccept/onDecline call behind a confirm step -- both
  // are a one-click irreversible commitment (accept locks this pair's side
  // of the cycle; decline drops it out of the cycle) with no undo anywhere
  // in the workflow. { pair, decision } | null.
  const [confirming, setConfirming] = useState(null)

  function confirmAndClose() {
    const { pair, decision } = confirming
    setConfirming(null)
    if (decision === "accepted") onAccept(pair)
    else onDecline(pair)
  }

  return (
    <Card>
      <Card.Header
        title={
          detailLinkTo ? (
            <Link to={detailLinkTo} className="hover:text-accent">
              Cycle · {nodes.length} pairs
            </Link>
          ) : (
            `Cycle · ${nodes.length} pairs`
          )
        }
        subtitle={`${proposal.policy.replace(/_/g, " ")} · weight ${proposal.weight.toFixed(1)} · expires ${new Date(
          proposal.expires_at
        ).toLocaleDateString()}`}
        action={<Badge status="neutral">{STATUS_LABELS[proposal.status] ?? proposal.status}</Badge>}
      />

      <div className="flex flex-col">
        {nodes.map((node) => {
          const pairRow = pairRowByDonorId.get(node.pair_id)
          const isMine = pairRow?.owning_doctor_id === currentDoctorId
          const isActionable =
            isMine && pairRow?.decision === "pending" && proposal.status === "proposed"

          return (
            <div
              key={node.pair_id}
              className="flex items-center justify-between gap-3 py-2 border-b border-border last:border-b-0"
            >
              <div className="min-w-0">
                <p className="text-[15px] font-semibold text-text">
                  {node.patient_blood_type}
                  <span className="text-text-muted font-normal"> recipient ← </span>
                  {node.donor_blood_type}
                  <span className="text-text-muted font-normal"> donor</span>
                </p>
                <p className="text-[13px] text-text-muted truncate">
                  {node.donor_hospital_name} · {node.donor_doctor_full_name}
                </p>
              </div>

              <div className="flex flex-col items-end gap-1.5 shrink-0">
                <Badge status="neutral">{DECISION_LABELS[pairRow?.decision] ?? "—"}</Badge>
                {isActionable && onAccept && onDecline && (
                  <div className="flex gap-1.5">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={isBusy}
                      onClick={() => setConfirming({ pair: pairRow, decision: "declined" })}
                    >
                      Decline
                    </Button>
                    <Button
                      size="sm"
                      disabled={isBusy}
                      onClick={() => setConfirming({ pair: pairRow, decision: "accepted" })}
                    >
                      Accept
                    </Button>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {canCancel && (
        <div className="mt-3 pt-3 border-t border-border flex justify-end">
          <Button size="sm" variant="secondary" disabled={isBusy} onClick={onCancel}>
            Cancel proposal
          </Button>
        </div>
      )}

      <Modal
        open={Boolean(confirming)}
        onClose={() => setConfirming(null)}
        title={confirming?.decision === "accepted" ? "Accept this pair?" : "Decline this pair?"}
      >
        <p className="text-[15px] text-text-muted">
          {confirming?.decision === "accepted"
            ? "This locks in your pair's side of the cycle. It can't be undone."
            : "This drops your pair out of this cycle. It can't be undone."}
        </p>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="secondary" onClick={() => setConfirming(null)}>
            Cancel
          </Button>
          <Button
            variant={confirming?.decision === "declined" ? "destructive" : "primary"}
            onClick={confirmAndClose}
          >
            {confirming?.decision === "accepted" ? "Accept" : "Decline"}
          </Button>
        </div>
      </Modal>
    </Card>
  )
}

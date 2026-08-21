// src/pages/ExchangeProposalsInboxPage.jsx
import { useCallback, useEffect, useState } from "react"
import { useAuth } from "../hooks/useAuth"
import {
  cancelExchangeProposal,
  decideExchangeProposalPair,
  listExchangeProposals,
} from "../api/exchangeProposals"
import ExchangeProposalCard from "../components/domain/exchange/ExchangeProposalCard"
import EmptyState from "../components/ui/EmptyState"
import SegmentedControl from "../components/ui/SegmentedControl"
import Spinner from "../components/ui/Spinner"

const SCOPE_OPTIONS = [
  { value: "mine", label: "Awaiting my decision" },
  { value: "all", label: "All open proposals" },
]

export default function ExchangeProposalsInboxPage() {
  const { user } = useAuth()
  const [scope, setScope] = useState("mine")
  const [proposals, setProposals] = useState(null)
  const [failed, setFailed] = useState(false)
  const [busyPairId, setBusyPairId] = useState(null)
  const [actionError, setActionError] = useState("")

  const load = useCallback(() => {
    let cancelled = false
    setFailed(false)
    listExchangeProposals(scope === "mine")
      .then((data) => !cancelled && setProposals(data))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [scope])

  useEffect(() => {
    setProposals(null)
    return load()
  }, [load])

  async function handleDecision(proposalId, pair, decision) {
    setBusyPairId(pair.id)
    setActionError("")
    try {
      await decideExchangeProposalPair(proposalId, pair.id, decision)
      load()
    } catch (err) {
      setActionError(err.message || "Couldn't record that decision. Please try again.")
    } finally {
      setBusyPairId(null)
    }
  }

  async function handleCancel(proposalId) {
    setBusyPairId(proposalId)
    setActionError("")
    try {
      await cancelExchangeProposal(proposalId)
      load()
    } catch (err) {
      setActionError(err.message || "Couldn't cancel this proposal. Please try again.")
    } finally {
      setBusyPairId(null)
    }
  }

  const status = proposals ? "loaded" : failed ? "error" : "loading"

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-[22px] font-bold text-text">Exchange proposals</h1>
        <p className="text-[14px] text-text-muted">
          Discovered cycles proposed for commitment. A cycle locks only once every pair's own
          doctor has accepted.
        </p>
      </div>

      <div className="max-w-xs">
        <SegmentedControl options={SCOPE_OPTIONS} value={scope} onChange={setScope} />
      </div>

      {actionError && (
        <p role="alert" className="text-[13px] text-high-risk font-medium">
          {actionError}
        </p>
      )}

      {status === "loading" && (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      )}

      {status === "error" && (
        <EmptyState message="Couldn't load exchange proposals. Please try refreshing." />
      )}

      {status === "loaded" &&
        (proposals.length === 0 ? (
          <EmptyState
            message={
              scope === "mine"
                ? "No proposals are awaiting your decision right now."
                : "No open exchange proposals right now."
            }
          />
        ) : (
          <div className="flex flex-col gap-4">
            {proposals.map((proposal) => (
              <ExchangeProposalCard
                key={proposal.id}
                proposal={proposal}
                currentDoctorId={user?.id}
                detailLinkTo={`/exchange/proposals/${proposal.id}`}
                isBusy={busyPairId !== null}
                onAccept={(pair) => handleDecision(proposal.id, pair, "accepted")}
                onDecline={(pair) => handleDecision(proposal.id, pair, "declined")}
                onCancel={
                  proposal.created_by_doctor_id === user?.id
                    ? () => handleCancel(proposal.id)
                    : null
                }
              />
            ))}
          </div>
        ))}
    </div>
  )
}

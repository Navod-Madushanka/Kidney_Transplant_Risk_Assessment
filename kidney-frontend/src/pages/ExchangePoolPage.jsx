// src/pages/ExchangePoolPage.jsx
import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { getExchangeCompare, getExchangeHardToMatch, getExchangeMatch } from "../api/exchange"
import { createExchangeProposal } from "../api/exchangeProposals"
import { DEFAULT_EXCHANGE_POLICY, EXCHANGE_POLICY_OPTIONS } from "../constants/exchangePolicies"
import ExchangeCycleGraph from "../components/domain/ExchangeCycleGraph"
import Badge from "../components/ui/Badge"
import Button from "../components/ui/Button"
import Card from "../components/ui/Card"
import EmptyState from "../components/ui/EmptyState"
import Modal from "../components/ui/Modal"
import SegmentedControl from "../components/ui/SegmentedControl"
import Select from "../components/ui/Select"
import Spinner from "../components/ui/Spinner"

const VIEW_MODE_OPTIONS = [
  { value: "single", label: "Single policy" },
  { value: "compare", label: "Compare" },
  { value: "hard-to-match", label: "Hard to match" },
]

const POLICY_LABEL_BY_VALUE = Object.fromEntries(
  EXCHANGE_POLICY_OPTIONS.map(({ value, label }) => [value, label])
)

// K7 verdicts, in the same priority order the backend applies them.
const VERDICT_LABELS = {
  no_donor_out: "No compatible recipient",
  no_donor_in: "No compatible donor",
  no_reciprocal_path: "No reciprocal path",
  lost_to_overlap: "Lost to an overlapping cycle",
}
const VERDICT_HINTS = {
  no_donor_out: "This pair's donor is incompatible with every recipient in the pool.",
  no_donor_in: "No donor in the pool can give to this patient — the sensitisation signal. Consider desensitisation or national referral.",
  no_reciprocal_path: "Has compatible edges, but sits in no 2- or 3-cycle.",
  lost_to_overlap: "Sits in a candidate cycle, but every policy preferred an overlapping one instead.",
}

export default function ExchangePoolPage() {
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState("single")
  const [proposingIndex, setProposingIndex] = useState(null)
  const [proposeError, setProposeError] = useState("")
  const [policy, setPolicy] = useState(DEFAULT_EXCHANGE_POLICY)
  // Keyed by the policy it was fetched for, so switching the dropdown falls
  // back to "loading" (rather than flashing the previous policy's result)
  // without resetting state synchronously inside the effect body.
  const [result, setResult] = useState(null)
  const [failedPolicy, setFailedPolicy] = useState(null)
  const [isGraphOpen, setGraphOpen] = useState(false)

  const [compareResult, setCompareResult] = useState(null)
  const [compareFailed, setCompareFailed] = useState(false)

  const [hardToMatchResult, setHardToMatchResult] = useState(null)
  const [hardToMatchFailed, setHardToMatchFailed] = useState(false)

  // Clears any stale failure for this exact policy the moment the dropdown
  // switches back to it (review #2 bug 23) -- failedPolicy used to only
  // ever be set (in the effect's .catch() below) and never reset, so
  // retrying a policy that had previously failed showed the old error
  // message the whole time the new request was in flight instead of the
  // loading spinner. Done as a render-time state adjustment (comparing
  // against the last-synced policy) rather than a setState call in the
  // effect body, so it takes effect before the browser paints instead of
  // costing a second commit.
  const [lastSyncedPolicy, setLastSyncedPolicy] = useState(policy)
  if (policy !== lastSyncedPolicy) {
    setLastSyncedPolicy(policy)
    setFailedPolicy((current) => (current === policy ? null : current))
  }

  useEffect(() => {
    if (viewMode !== "single") return
    let cancelled = false

    getExchangeMatch(policy)
      .then((data) => !cancelled && setResult({ policy, data }))
      .catch(() => !cancelled && setFailedPolicy(policy))

    return () => {
      cancelled = true
    }
  }, [viewMode, policy])

  useEffect(() => {
    if (viewMode !== "compare" || compareResult) return
    let cancelled = false

    getExchangeCompare()
      .then((data) => !cancelled && setCompareResult(data))
      .catch(() => !cancelled && setCompareFailed(true))

    return () => {
      cancelled = true
    }
  }, [viewMode, compareResult])

  useEffect(() => {
    if (viewMode !== "hard-to-match" || hardToMatchResult) return
    let cancelled = false

    getExchangeHardToMatch()
      .then((data) => !cancelled && setHardToMatchResult(data))
      .catch(() => !cancelled && setHardToMatchFailed(true))

    return () => {
      cancelled = true
    }
  }, [viewMode, hardToMatchResult])

  const data = result?.policy === policy ? result.data : null
  const status = data ? "loaded" : failedPolicy === policy ? "error" : "loading"
  const selectedCycles = data?.selected_cycles ?? []
  const nodeByPairId = new Map((data?.nodes ?? []).map((node) => [node.pair_id, node]))
  const edgeByKey = new Map(
    (data?.edges ?? []).map((edge) => [`${edge.from_pair_id}->${edge.to_pair_id}`, edge])
  )

  const compareStatus = compareResult ? "loaded" : compareFailed ? "error" : "loading"
  const compareNodeByPairId = new Map(
    (compareResult?.nodes ?? []).map((node) => [node.pair_id, node])
  )
  const compareEdgeByKey = new Map(
    (compareResult?.edges ?? []).map((edge) => [`${edge.from_pair_id}->${edge.to_pair_id}`, edge])
  )

  const hardToMatchStatus = hardToMatchResult ? "loaded" : hardToMatchFailed ? "error" : "loading"

  async function handlePropose(cycle, index) {
    setProposeError("")
    setProposingIndex(index)
    try {
      const proposal = await createExchangeProposal(policy, cycle.pair_ids)
      navigate(`/exchange/proposals/${proposal.id}`)
    } catch (err) {
      setProposeError(err.message || "Couldn't propose this cycle. Please try again.")
      setProposingIndex(null)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <h1 className="text-[22px] font-bold text-text">Paired exchange pool</h1>
          <Link to="/exchange/proposals" className="text-[13px] font-semibold text-accent hover:text-accent-hover">
            View proposals →
          </Link>
        </div>
        <p className="text-[14px] text-text-muted">
          Every registered donor/intended-recipient pair that's ABO/HLA/DSA-incompatible on its
          own, and the best cycle of swaps the selected policy can find among them. Advisory
          only — nothing here changes any donor or patient's status.
        </p>
      </div>

      <div className="max-w-xs">
        <SegmentedControl
          label="View"
          options={VIEW_MODE_OPTIONS}
          value={viewMode}
          onChange={setViewMode}
        />
      </div>

      {viewMode === "single" && (
        <>
          <div className="max-w-xs">
            <Select
              label="Optimization policy"
              value={policy}
              onChange={(event) => setPolicy(event.target.value)}
              options={EXCHANGE_POLICY_OPTIONS.map(({ value, label }) => ({ value, label }))}
            />
            <p className="mt-1.5 text-[13px] text-text-muted">
              {EXCHANGE_POLICY_OPTIONS.find((option) => option.value === policy)?.description}
            </p>
          </div>

          {status === "loading" && (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          )}

          {status === "error" && (
            <EmptyState message="Couldn't load the exchange pool. Please try refreshing." />
          )}

          {status === "loaded" && data && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <StatTile label="Incompatible pairs" value={data.nodes.length} />
                {/* "Selected", not "found" (review #2 bug 20) -- the API only
                    ever returns the solver's already-selected cycle set, not a
                    separate count of every candidate cycle it considered. */}
                <StatTile label="Cycles selected" value={selectedCycles.length} />
                <StatTile
                  label="Pairs transplanted"
                  value={selectedCycles.reduce((sum, cycle) => sum + cycle.pair_ids.length, 0)}
                />
              </div>

              {/* The graph is a desktop affordance (K10): a 40-node circular
                  SVG isn't a phone interface, and the cards below carry
                  every fact it does. Below md, a button opens it full-screen
                  in a sheet instead -- no pan/zoom, just the same read-only
                  view. */}
              <div className="hidden md:block">
                <ExchangeCycleGraph nodes={data.nodes} edges={data.edges} selectedCycles={selectedCycles} />
              </div>
              {data.nodes.length > 0 && (
                <div className="md:hidden">
                  <Button variant="secondary" size="sm" onClick={() => setGraphOpen(true)}>
                    View graph
                  </Button>
                </div>
              )}

              {proposeError && (
                <p className="text-[13px] text-high-risk font-medium">{proposeError}</p>
              )}

              {selectedCycles.length === 0 ? (
                <EmptyState message="No cycles selected under this policy right now." />
              ) : (
                <div className="flex flex-col gap-4">
                  {selectedCycles.map((cycle, index) => (
                    <Card key={index}>
                      <Card.Header
                        title={`Cycle #${index + 1}`}
                        subtitle={`${cycle.pair_ids.length} pairs · weight ${cycle.weight.toFixed(1)}`}
                        action={
                          <Button
                            size="sm"
                            loading={proposingIndex === index}
                            disabled={proposingIndex !== null}
                            onClick={() => handlePropose(cycle, index)}
                          >
                            Propose this cycle
                          </Button>
                        }
                      />
                      <CycleChain
                        pairIds={cycle.pair_ids}
                        nodeByPairId={nodeByPairId}
                        edgeByKey={edgeByKey}
                      />
                    </Card>
                  ))}
                </div>
              )}

              <Modal
                variant="sheet"
                open={isGraphOpen}
                onClose={() => setGraphOpen(false)}
                title="Exchange graph"
                className="max-h-[85vh] overflow-y-auto"
              >
                <ExchangeCycleGraph nodes={data.nodes} edges={data.edges} selectedCycles={selectedCycles} />
              </Modal>
            </>
          )}
        </>
      )}

      {viewMode === "compare" && (
        <>
          <p className="text-[13px] text-text-muted -mt-2">
            Every candidate cycle any policy selects, and which policies agree on it. A cycle
            every policy picks is robust; one only a single policy picks is a policy artefact.
          </p>

          {compareStatus === "loading" && (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          )}

          {compareStatus === "error" && (
            <EmptyState message="Couldn't load the policy comparison. Please try refreshing." />
          )}

          {compareStatus === "loaded" && compareResult && (
            <>
              {compareResult.cycles.length === 0 ? (
                <EmptyState message="No policy selects any cycle in the pool right now." />
              ) : (
                <div className="flex flex-col gap-4">
                  {[...compareResult.cycles]
                    .sort((a, b) => b.selected_by.length - a.selected_by.length)
                    .map((cycle, index) => (
                      <Card key={index}>
                        <Card.Header
                          title={`Candidate cycle · ${cycle.pair_ids.length} pairs`}
                          subtitle={`Selected by ${cycle.selected_by.length} of ${compareResult.policies.length} policies`}
                          action={
                            <div className="flex flex-wrap justify-end gap-1.5">
                              {cycle.selected_by.map((policyValue) => (
                                <Badge key={policyValue} status="pending">
                                  {POLICY_LABEL_BY_VALUE[policyValue] ?? policyValue}
                                </Badge>
                              ))}
                            </div>
                          }
                        />
                        <CycleChain
                          pairIds={cycle.pair_ids}
                          nodeByPairId={compareNodeByPairId}
                          edgeByKey={compareEdgeByKey}
                        />
                      </Card>
                    ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {viewMode === "hard-to-match" && (
        <>
          <p className="text-[13px] text-text-muted -mt-2">
            Pool pairs no policy selects under any weighting — the desensitisation / national-
            referral worklist. Sorted by longest real waiting time first.
          </p>

          {hardToMatchStatus === "loading" && (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          )}

          {hardToMatchStatus === "error" && (
            <EmptyState message="Couldn't load the hard-to-match worklist. Please try refreshing." />
          )}

          {hardToMatchStatus === "loaded" && hardToMatchResult && (
            <>
              {hardToMatchResult.pairs.length === 0 ? (
                <EmptyState message="Every pool pair is matched by at least one policy right now." />
              ) : (
                <div className="flex flex-col gap-3">
                  {hardToMatchResult.pairs.map((pair) => (
                    <Card key={pair.node.pair_id}>
                      <Card.Header
                        title={`${pair.node.patient_blood_type} recipient ← ${pair.node.donor_blood_type} donor`}
                        subtitle={`${pair.node.patient_hospital_name} · waiting ${pair.wait_days}d · cPRA ${
                          pair.cpra_percentage ?? "—"
                        }%`}
                        action={<Badge status="neutral">{VERDICT_LABELS[pair.verdict] ?? pair.verdict}</Badge>}
                      />
                      <p className="text-[13px] text-text-muted">
                        {VERDICT_HINTS[pair.verdict]}
                      </p>
                    </Card>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

function StatTile({ label, value }) {
  return (
    <div className="border border-border rounded-lg bg-surface p-4">
      <p className="text-xs leading-tight text-text-muted sm:text-[13px]">{label}</p>
      <p className="text-xl font-bold text-text tabular-nums sm:text-[24px]">{value}</p>
    </div>
  )
}

// A cycle as a vertical chain of pairs, closing back to the first -- the
// primary representation of a cycle at every breakpoint (K10: "do not build
// two representations of a cycle"), and shared between the single-policy
// view and K8's cross-policy comparison view so both render a cycle
// identically.
function CycleChain({ pairIds, nodeByPairId, edgeByKey }) {
  const hops = pairIds.map((pairId, index) => {
    const nextPairId = pairIds[(index + 1) % pairIds.length]
    return {
      pairId,
      node: nodeByPairId.get(pairId),
      edge: edgeByKey.get(`${pairId}->${nextPairId}`),
    }
  })

  return (
    <div className="flex flex-col">
      {hops.map((hop, index) => (
        <div key={hop.pairId} className="flex flex-col">
          <div className="flex items-center justify-between gap-3 py-2">
            <div className="min-w-0">
              <p className="text-[15px] font-semibold text-text">
                {hop.node?.patient_blood_type ?? "?"}
                <span className="text-text-muted font-normal"> recipient ← </span>
                {hop.node?.donor_blood_type ?? "?"}
                <span className="text-text-muted font-normal"> donor</span>
              </p>
              <p className="text-[13px] text-text-muted truncate">
                {hop.node?.donor_hospital_name} · {hop.node?.donor_doctor_full_name}
              </p>
            </div>
            {hop.edge && (
              <div className="flex flex-col items-end gap-1 shrink-0">
                <Badge status="neutral">
                  {hop.edge.mismatch_result?.total_mismatches ?? "?"} mismatch
                  {hop.edge.mismatch_result?.total_mismatches === 1 ? "" : "es"}
                </Badge>
                {hop.edge.dsa_result?.requires_review && (
                  <Badge status="moderate">DSA review</Badge>
                )}
              </div>
            )}
          </div>
          {index < hops.length - 1 ? (
            <p className="text-[12px] text-text-muted pl-1">↓ gives to next pair's recipient</p>
          ) : (
            <p className="text-[12px] text-accent pl-1">↺ closes back to the first pair</p>
          )}
        </div>
      ))}
    </div>
  )
}

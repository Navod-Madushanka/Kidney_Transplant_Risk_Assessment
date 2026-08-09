// src/pages/ExchangePoolPage.jsx
import { useEffect, useState } from "react"
import { getExchangeMatch } from "../api/exchange"
import { DEFAULT_EXCHANGE_POLICY, EXCHANGE_POLICY_OPTIONS } from "../constants/exchangePolicies"
import ExchangeCycleGraph from "../components/domain/ExchangeCycleGraph"
import Select from "../components/ui/Select"
import Table from "../components/ui/Table"

export default function ExchangePoolPage() {
  const [policy, setPolicy] = useState(DEFAULT_EXCHANGE_POLICY)
  // Keyed by the policy it was fetched for, so switching the dropdown falls
  // back to "loading" (rather than flashing the previous policy's result)
  // without resetting state synchronously inside the effect body.
  const [result, setResult] = useState(null)
  const [failedPolicy, setFailedPolicy] = useState(null)

  useEffect(() => {
    let cancelled = false

    getExchangeMatch(policy)
      .then((data) => !cancelled && setResult({ policy, data }))
      .catch(() => !cancelled && setFailedPolicy(policy))

    return () => {
      cancelled = true
    }
  }, [policy])

  const data = result?.policy === policy ? result.data : null
  const status = data ? "loaded" : failedPolicy === policy ? "error" : "loading"
  const selectedCycles = data?.selected_cycles ?? []
  const nodeByPairId = new Map((data?.nodes ?? []).map((node) => [node.pair_id, node]))

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <div className="flex flex-col gap-1">
        <h1 className="text-[22px] font-bold text-text">Paired exchange pool</h1>
        <p className="text-[14px] text-text-muted">
          Every registered donor/intended-recipient pair that's ABO/HLA/DSA-incompatible on its
          own, and the best cycle of swaps the selected policy can find among them. Advisory
          only — nothing here changes any donor or patient's status.
        </p>
      </div>

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
          <div
            className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin"
            role="status"
            aria-label="Loading"
          />
        </div>
      )}

      {status === "error" && (
        <div className="border border-border rounded-lg p-8 text-center bg-surface">
          <p className="text-[15px] text-text-muted">
            Couldn't load the exchange pool. Please try refreshing.
          </p>
        </div>
      )}

      {status === "loaded" && data && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <StatTile label="Incompatible pairs" value={data.nodes.length} />
            <StatTile label="Cycles found" value={selectedCycles.length} />
            <StatTile
              label="Pairs transplanted"
              value={selectedCycles.reduce((sum, cycle) => sum + cycle.pair_ids.length, 0)}
            />
          </div>

          <ExchangeCycleGraph nodes={data.nodes} edges={data.edges} selectedCycles={selectedCycles} />

          {selectedCycles.length > 0 && (
            <Table
              columns={[
                { key: "cycle", label: "Cycle" },
                { key: "size", label: "Pairs", align: "right" },
                { key: "weight", label: "Weight", align: "right" },
                { key: "members", label: "Members" },
              ]}
              rows={selectedCycles.map((cycle, index) => ({ ...cycle, cycleNumber: index + 1 }))}
              getRowId={(cycle) => cycle.cycleNumber}
              renderCell={(cycle, col) => {
                switch (col.key) {
                  case "cycle":
                    return `#${cycle.cycleNumber}`
                  case "size":
                    return cycle.pair_ids.length
                  case "weight":
                    return cycle.weight.toFixed(1)
                  case "members":
                    return cycle.pair_ids
                      .map((pairId) => {
                        const node = nodeByPairId.get(pairId)
                        return node ? `${node.patient_blood_type}←${node.donor_blood_type}` : pairId
                      })
                      .join("  →  ")
                  default:
                    return null
                }
              }}
            />
          )}
        </>
      )}
    </div>
  )
}

function StatTile({ label, value }) {
  return (
    <div className="border border-border rounded-lg bg-surface p-4">
      <p className="text-[13px] text-text-muted">{label}</p>
      <p className="text-[24px] font-bold text-text tabular-nums">{value}</p>
    </div>
  )
}

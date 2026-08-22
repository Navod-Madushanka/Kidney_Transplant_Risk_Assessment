// src/constants/exchangePolicies.js
//
// Mirrors kidney-backend/app/services/exchange_matching_service.py::WEIGHT_
// POLICIES. Each policy picks a different maximum-weight set of non-
// overlapping exchange cycles from the same candidate graph — see that
// module's weight_max_transplants/weight_max_quality/weight_equity for what
// each one actually optimizes.

export const EXCHANGE_POLICY_OPTIONS = [
  {
    value: "max_transplants",
    label: "Max transplants",
    description: "Packs the most pairs into cycles, regardless of match quality.",
  },
  {
    value: "max_quality",
    label: "Max quality",
    description: "Prefers cycles with fewer HLA mismatches, even if fewer pairs transplant.",
  },
  {
    value: "equity_weighted",
    label: "Equity-weighted",
    description: "Adds a bonus for highly sensitised and longer-waiting patients.",
  },
  {
    value: "max_lkdpi_quality",
    label: "Max donor quality (LKDPI)",
    description: "Prefers cycles with lower Living Kidney Donor Profile Index scores.",
  },
]

export const DEFAULT_EXCHANGE_POLICY = "max_transplants"

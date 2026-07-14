// src/constants/riskTiers.js
//
// Mirrors the backend's RISK_TIERS boundaries (see
// kidney-backend/app/reference_data/risk_tiers.py) so this page can derive
// a risk tier label from hla_scoring_result.total_score the same way
// dashboard_service.py's _derive_risk_tier does server-side — MatchReport
// doesn't persist risk_tier as its own column, only the raw scoring JSON.
// If the backend boundaries ever change, update both places together.

const RISK_TIERS = [
  { name: "Low Risk", minScore: 0.0, maxScore: 2.0 },
  { name: "Moderate Risk", minScore: 2.25, maxScore: 5.0 },
  { name: "High-Moderate Risk", minScore: 5.25, maxScore: 7.0 },
  { name: "High Genetic Risk", minScore: 7.25, maxScore: 10.0 },
]

export function deriveRiskTier(hlaScoringResult) {
  if (!hlaScoringResult) return null
  const score = hlaScoringResult.total_score
  const tier = RISK_TIERS.find((t) => score >= t.minScore && score <= t.maxScore)
  return tier?.name ?? null
}
// src/api/exchangeProposals.js
import { apiGet, apiPost } from "./client"

export const createExchangeProposal = (policy, pairIds) =>
  apiPost("/exchange/proposals", { policy, pair_ids: pairIds })

export const listExchangeProposals = (mine = false) =>
  apiGet(mine ? "/exchange/proposals?mine=true" : "/exchange/proposals")

export const getExchangeProposal = (proposalId) => apiGet(`/exchange/proposals/${proposalId}`)

export const decideExchangeProposalPair = (proposalId, pairId, decision, declineReason = null) =>
  apiPost(`/exchange/proposals/${proposalId}/pairs/${pairId}/decision`, {
    decision,
    decline_reason: declineReason,
  })

export const cancelExchangeProposal = (proposalId) =>
  apiPost(`/exchange/proposals/${proposalId}/cancel`)

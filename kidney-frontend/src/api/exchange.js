// src/api/exchange.js
import { apiGet } from "./client"

export const getExchangeMatch = (policy) =>
  apiGet(`/exchange/match?policy=${encodeURIComponent(policy)}`)

export const getExchangeCompare = () => apiGet("/exchange/match/compare")

export const getExchangeHardToMatch = () => apiGet("/exchange/hard-to-match")

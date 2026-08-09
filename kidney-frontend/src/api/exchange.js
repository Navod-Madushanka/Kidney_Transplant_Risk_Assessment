// src/api/exchange.js
import { apiGet } from "./client"

export const getExchangeMatch = (policy) =>
  apiGet(`/exchange/match?policy=${encodeURIComponent(policy)}`)

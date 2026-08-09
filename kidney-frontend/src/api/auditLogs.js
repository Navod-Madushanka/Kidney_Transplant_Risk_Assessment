// src/api/auditLogs.js
// Admin-only (review #2 bug 12) -- kidney-backend/app/api/audit_logs.py
// gates both of these behind require_admin, so a non-admin doctor gets a
// 403 ApiError from either call, not a 401 (they're authenticated, just
// not authorized). AuditLogPage.jsx surfaces that distinctly.
import { apiGet } from "./client"

export const listAuditLogs = (limit = 50, offset = 0) =>
  apiGet(`/audit-logs?limit=${limit}&offset=${offset}`)

export const verifyAuditChain = () => apiGet("/audit-logs/verify")

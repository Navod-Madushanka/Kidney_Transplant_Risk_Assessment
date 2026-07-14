// src/api/reports.js
import { apiGet } from "./client"

export const getReport = (reportId) => apiGet(`/compatibility/reports/${reportId}`)
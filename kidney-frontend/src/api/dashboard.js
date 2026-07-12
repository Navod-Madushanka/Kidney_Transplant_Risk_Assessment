// src/api/dashboard.js
import { apiGet } from "./client"

export const getDashboardPatients = () => apiGet("/dashboard/patients")
export const getDashboardRecentReports = (limit = 5) =>
  apiGet(`/dashboard/reports/recent?limit=${limit}`)
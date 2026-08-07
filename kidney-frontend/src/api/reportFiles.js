// src/api/reportFiles.js
// Wrappers for the report-file attachment endpoints — a plain document
// archive for patients/donors (upload/list/download/delete), separate from
// the OCR extraction flow in ocr.js. Kept in its own file rather than split
// across patients.js/donors.js since the one ReportFilesCard consumer needs
// both patient and donor variants side by side.
import { apiDelete, apiDownloadFile, apiGet, apiGetBlob, apiPostForm } from "./client"

function buildUploadForm(category, file) {
  const formData = new FormData()
  formData.append("category", category)
  formData.append("file", file)
  return formData
}

export const listPatientReportFiles = (patientId) =>
  apiGet(`/patients/${patientId}/report-files`)
export const uploadPatientReportFile = (patientId, category, file) =>
  apiPostForm(`/patients/${patientId}/report-files`, buildUploadForm(category, file))
export const deletePatientReportFile = (patientId, id) =>
  apiDelete(`/patients/${patientId}/report-files/${id}`)
export const downloadPatientReportFile = (patientId, id, filename) =>
  apiDownloadFile(`/patients/${patientId}/report-files/${id}/download`, filename)
export const fetchPatientReportFileBlob = (patientId, id) =>
  apiGetBlob(`/patients/${patientId}/report-files/${id}/download`)

export const listDonorReportFiles = (donorId) => apiGet(`/donors/${donorId}/report-files`)
export const uploadDonorReportFile = (donorId, category, file) =>
  apiPostForm(`/donors/${donorId}/report-files`, buildUploadForm(category, file))
export const deleteDonorReportFile = (donorId, id) =>
  apiDelete(`/donors/${donorId}/report-files/${id}`)
export const downloadDonorReportFile = (donorId, id, filename) =>
  apiDownloadFile(`/donors/${donorId}/report-files/${id}/download`, filename)
export const fetchDonorReportFileBlob = (donorId, id) =>
  apiGetBlob(`/donors/${donorId}/report-files/${id}/download`)

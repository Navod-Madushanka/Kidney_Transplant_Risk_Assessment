// src/api/client.js
// Falls back to 8000 (the backend's actual default: see kidney-backend's
// Dockerfile EXPOSE/CMD and README uvicorn command) when VITE_API_BASE_URL
// isn't set. This used to default to 8090, which doesn't match the backend
// anywhere — every request would 404/fail-to-connect out of the box unless
// a .env explicitly overrode it.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
const SESSION_KEY = "kts_session" // { access_token, email, full_name?, hospital_name? }

let onAuthExpired = null
export function setOnAuthExpired(callback) {
  onAuthExpired = callback
}

export function readSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function writeSession(session) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export function clearSession() {
  sessionStorage.removeItem(SESSION_KEY)
}

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.data = data
  }
}

// FastAPI's error body is `{ detail: ... }`, but `detail` isn't always a
// string — a 422 validation failure sends a list of
// { loc, msg, type } objects. Passed straight to `new Error(...)`, a
// non-string message stringifies to "[object Object]" wherever it's
// rendered, so this always resolves to readable text instead.
function extractErrorMessage(data, status) {
  const detail = data?.detail ?? data?.message
  if (typeof detail === "string") return detail

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item
        const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : null
        return field ? `${field}: ${item.msg}` : item?.msg
      })
      .filter(Boolean)
    if (messages.length > 0) return messages.join("; ")
  }

  if (detail && typeof detail === "object" && typeof detail.msg === "string") {
    return detail.msg
  }

  return `Request failed (${status})`
}

async function request(path, { method = "GET", body } = {}) {
  const session = readSession()
  const headers = { "Content-Type": "application/json" }
  if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 401) {
    clearSession()
    onAuthExpired?.()
  }

  // FastAPI sends `content-type: application/json` even on a bodyless 204
  // (e.g. every DELETE endpoint) — response.json() throws SyntaxError on an
  // empty body, so 204 always skips the parse regardless of the header.
  let data = null
  const contentType = response.headers.get("content-type") || ""
  if (response.status !== 204 && contentType.includes("application/json")) {
    data = await response.json()
  }

  if (!response.ok) {
    throw new ApiError(extractErrorMessage(data, response.status), response.status, data)
  }

  return data
}

async function requestFormData(path, formData) {
  const session = readSession()
  const headers = {}
  if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`
  // Deliberately no Content-Type here — the browser sets the multipart
  // boundary itself when the body is a FormData instance. Setting it
  // manually breaks the upload.

  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: formData,
  })

  if (response.status === 401) {
    clearSession()
    onAuthExpired?.()
  }

  let data = null
  const contentType = response.headers.get("content-type") || ""
  if (contentType.includes("application/json")) {
    data = await response.json()
  }

  if (!response.ok) {
    throw new ApiError(extractErrorMessage(data, response.status), response.status, data)
  }

  return data
}

export const apiPostForm = (path, formData) => requestFormData(path, formData)

export const apiGet = (path) => request(path, { method: "GET" })
export const apiPost = (path, body) => request(path, { method: "POST", body })
export const apiPut = (path, body) => request(path, { method: "PUT", body })
export const apiDelete = (path) => request(path, { method: "DELETE" })

// Downloads a binary response (e.g. a report file) with the auth header
// attached — a plain <a href> can't carry that header, so this fetches as a
// blob and triggers a synthetic download instead. `filename` is supplied by
// the caller (already known from the file's own metadata) rather than
// parsed back out of Content-Disposition, since that header isn't in the
// browser's default CORS-exposed-headers safelist and would silently come
// back empty cross-origin.
export async function apiDownloadFile(path, filename) {
  const session = readSession()
  const headers = {}
  if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`

  const response = await fetch(`${BASE_URL}${path}`, { headers })

  if (response.status === 401) {
    clearSession()
    onAuthExpired?.()
  }

  if (!response.ok) {
    let data = null
    const contentType = response.headers.get("content-type") || ""
    if (contentType.includes("application/json")) data = await response.json()
    throw new ApiError(extractErrorMessage(data, response.status), response.status, data)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
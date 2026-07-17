// src/api/client.js
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8090"
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

  let data = null
  const contentType = response.headers.get("content-type") || ""
  if (contentType.includes("application/json")) {
    data = await response.json()
  }

  if (!response.ok) {
    throw new ApiError(
      data?.detail || data?.message || `Request failed (${response.status})`,
      response.status,
      data
    )
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
    throw new ApiError(
      data?.detail || data?.message || `Request failed (${response.status})`,
      response.status,
      data
    )
  }

  return data
}

export const apiPostForm = (path, formData) => requestFormData(path, formData)

export const apiGet = (path) => request(path, { method: "GET" })
export const apiPost = (path, body) => request(path, { method: "POST", body })
export const apiPut = (path, body) => request(path, { method: "PUT", body })
export const apiDelete = (path) => request(path, { method: "DELETE" })
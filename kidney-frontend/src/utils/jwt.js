// src/utils/jwt.js

// Decodes the JWT payload client-side for UI purposes only (role, hospital_id,
// expiry). This is NOT verification — the server still validates the
// signature on every request. Never make an authorization decision here that
// the backend doesn't also enforce.
export function decodeJwt(token) {
  try {
    const payload = token.split(".")[1]
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/")
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=")
    const json = decodeURIComponent(
      atob(padded)
        .split("")
        .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
        .join("")
    )
    return JSON.parse(json)
  } catch {
    return null
  }
}

export function isTokenExpired(claims) {
  if (!claims?.exp) return true
  return Date.now() >= claims.exp * 1000
}
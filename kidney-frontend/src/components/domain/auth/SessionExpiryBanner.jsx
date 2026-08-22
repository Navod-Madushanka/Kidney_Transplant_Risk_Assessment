// src/components/domain/auth/SessionExpiryBanner.jsx
import { useCallback, useEffect, useState } from "react"
import { useAuth } from "../../../hooks/useAuth"
import { ApiError } from "../../../api/client"
import Modal from "../../ui/Modal"
import InputField from "../../ui/InputField"
import Button from "../../ui/Button"

// Phase 3.5 (FINALIZATION-PLAN.md): warns before the JWT's fixed 60-minute
// expiry (access_token_expire_minutes, kidney-backend/app/core/config.py)
// rather than letting a doctor discover it mid-task when an API call
// suddenly 401s. Timed off AuthProvider's expiresAt (the token's own `exp`
// claim, decoded client-side -- see utils/jwt.js), not a fixed 55-minute
// timer, so it stays correct even if that backend setting ever changes.
const WARNING_LEAD_MS = 5 * 60 * 1000

function minutesUntil(expiresAt) {
  return Math.max(0, Math.round((expiresAt - Date.now()) / 60000))
}

function isPastWarningThreshold(status, expiresAt) {
  return status === "authenticated" && !!expiresAt && Date.now() >= expiresAt - WARNING_LEAD_MS
}

export default function SessionExpiryBanner() {
  const { status, expiresAt, user, login, logout } = useAuth()
  // Lazy initializers, not plain `useState(false)`/`useState(0)`: a doctor
  // whose token was already inside the warning window before this
  // component ever mounted (e.g. a page reload at minute 57) must see the
  // warning -- with a correct minute count -- on the very first paint, not
  // one tick later once the effect below's setTimeout(…, 0) gets around to
  // firing. ProtectedRoute only ever renders this component while
  // status === "authenticated" (see its own render logic), and unmounts it
  // on logout, so a fresh login always gets a fresh mount here -- neither
  // state below needs a reset path for "no longer authenticated".
  const [isWarning, setIsWarning] = useState(() => isPastWarningThreshold(status, expiresAt))
  const [minutesLeft, setMinutesLeft] = useState(() => (expiresAt ? minutesUntil(expiresAt) : 0))
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (status !== "authenticated" || !expiresAt) return

    const now = Date.now()
    // Re-authenticating (see handleReauth below) dispatches a fresh
    // AUTHENTICATED with a new expiresAt, which re-runs this effect and
    // pushes both timers back out -- a doctor who stays signed in never
    // sees a second warning for the same session.
    const warnTimer = setTimeout(
      () => {
        setIsWarning(true)
        setMinutesLeft(minutesUntil(expiresAt))
      },
      Math.max(expiresAt - WARNING_LEAD_MS - now, 0)
    )
    // Proactive sign-out at the real expiry instant: apiClient's
    // onAuthExpired (see api/client.js) only fires when a 401 actually
    // comes back from a request in flight -- a doctor who's read-only idle
    // when the token expires would otherwise keep seeing a stale
    // "signed in" UI until their next API call.
    const expireTimer = setTimeout(() => logout(), Math.max(expiresAt - now, 0))

    return () => {
      clearTimeout(warnTimer)
      clearTimeout(expireTimer)
    }
  }, [status, expiresAt, logout])

  // Stable reference, not a fresh arrow function every render: Modal's own
  // focus-management effect re-runs whenever its `onClose` prop changes
  // identity (see Modal.jsx), and an inline `() => setIsWarning(false)`
  // here would recreate that identity on every keystroke in the password
  // field below (each one re-renders this component via setPassword),
  // which re-ran that effect and stole focus back to the dialog after
  // every single character -- found by this component's own test suite
  // (typing more than one character into the field silently only kept
  // the first).
  const dismissWarning = useCallback(() => setIsWarning(false), [])

  if (!isWarning || status !== "authenticated") return null

  async function handleReauth(e) {
    e.preventDefault()
    setError("")
    setIsSubmitting(true)
    try {
      await login(user.email, password)
      setIsWarning(false)
      setPassword("")
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Incorrect password.")
      } else if (err instanceof ApiError && err.status === 429) {
        setError(err.message)
      } else {
        setError("Something went wrong. Please try again.")
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal open onClose={dismissWarning} title="Your session is about to expire">
      <p className="text-[14px] text-text-muted">
        You'll be signed out in about {minutesLeft} minute{minutesLeft === 1 ? "" : "s"}. Enter
        your password to stay signed in without losing your place.
      </p>
      <form onSubmit={handleReauth} className="mt-4 flex flex-col gap-3">
        <InputField
          label="Password"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={error}
          required
        />
        <div className="flex justify-end gap-2 mt-2">
          <Button type="button" variant="secondary" onClick={logout}>
            Sign out
          </Button>
          <Button type="submit" loading={isSubmitting}>
            Stay signed in
          </Button>
        </div>
      </form>
    </Modal>
  )
}

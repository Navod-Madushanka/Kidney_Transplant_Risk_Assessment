# app/services/login_throttle_service.py
"""
In-memory login throttling for POST /auth/login (B9 / Phase 3.2 of
FINALIZATION-PLAN.md).

Single-process, in-memory state -- matches this deployment's single-worker,
single-host topology (see docker-compose.prod.yml's kidney-backend command
comment, and app/main.py's lifespan docstring making the same assumption
for its own startup reconciliation). A multi-worker or multi-host
deployment would need this moved to a shared store (e.g. Redis -- already
reserved for future use, see app/core/config.py's redis_url) since each
worker would otherwise keep its own independent counters and only see 1/N
of real traffic against any one account or IP. Flagged here rather than
silently wrong if that assumption ever changes.

Two independent counters, both keyed by a normalized identity string:
- Per-account (lowercased email): stops a single account being brute-forced
  regardless of which IP the attempts come from.
- Per-IP: stops one source hammering many different accounts, which a
  per-account-only limiter would never notice since no single account ever
  crosses its own threshold.
Both must be clear (not locked) for a login attempt to reach password
verification at all -- see app/api/auth.py's login(). Failed attempts
against a *nonexistent* email still count against both counters (the
response is identical either way, so this doesn't leak which emails are
real accounts); a lockout is never logged to app.services.audit_service's
audit_logs table, since that table's doctor_id column is NOT NULL and
foreign-keyed to a real Doctor row -- an unknown-email attempt has no
doctor to attach the entry to, and conflating "who did what to which
patient" with "what did an anonymous client attempt" would blur what that
table is for. These events go to the structured application log instead
(app/core/logging.py) -- see the logger.warning calls in auth.py's login().
"""
import time
from dataclasses import dataclass
from threading import Lock

# First MAX_FAILURES-1 failures are counted but never lock the account/IP
# out -- a doctor who fat-fingers their password twice shouldn't be locked
# out on the third correct attempt.
MAX_ACCOUNT_FAILURES_BEFORE_LOCK = 5
# Higher than the per-account threshold: a hospital's outbound traffic
# often NATs through one gateway IP, so many different doctors legitimately
# share one apparent source IP. This threshold exists to catch someone
# spraying attempts across many accounts from one source, not to further
# restrict ordinary shared-IP traffic.
MAX_IP_FAILURES_BEFORE_LOCK = 20

LOCKOUT_BASE_SECONDS = 30.0
LOCKOUT_MAX_SECONDS = 900.0  # 15 minutes

# An entry with no lock in force and no failure in this long is dropped on
# the next prune pass, so long-lived process memory doesn't grow forever
# across months of real traffic. Purely a memory-hygiene cutoff -- has no
# effect on lockout behavior itself (a fresh attempt after this long starts
# a fresh count either way, lock or no lock).
STALE_ENTRY_SECONDS = 24 * 3600.0


@dataclass
class _ThrottleState:
    failure_count: int = 0
    locked_until: float = 0.0
    last_failure_at: float = 0.0


class LoginThrottle:
    """One instance per counter dimension (account, IP) -- see module
    docstring. time.monotonic() throughout: this only ever measures
    durations within one process's lifetime, never wall-clock instants, so
    it can't be fooled by an NTP correction the way audit_service's
    hash-chain ordering explicitly had to guard against for created_at.
    """

    def __init__(self, max_failures: int):
        self._max_failures = max_failures
        self._state: dict[str, _ThrottleState] = {}
        self._lock = Lock()

    def seconds_until_unlocked(self, key: str) -> float:
        with self._lock:
            state = self._state.get(key)
            if state is None:
                return 0.0
            remaining = state.locked_until - time.monotonic()
            return remaining if remaining > 0 else 0.0

    def record_failure(self, key: str) -> float:
        """Records one failed attempt against `key`. Returns the lockout
        duration in seconds just applied, or 0.0 if this failure didn't
        (yet) cross the threshold.
        """
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            state = self._state.setdefault(key, _ThrottleState())
            state.failure_count += 1
            state.last_failure_at = now

            if state.failure_count < self._max_failures:
                return 0.0

            # Exponential backoff from the threshold, not from zero: the
            # Nth failure at the threshold locks for LOCKOUT_BASE_SECONDS,
            # each one after that doubles, capped at LOCKOUT_MAX_SECONDS --
            # so a one-off lockout is short, but a sustained attacker
            # (or a compromised credential being sprayed) faces a lock that
            # keeps growing rather than resetting to the same short delay
            # every time.
            exponent = state.failure_count - self._max_failures
            duration = min(LOCKOUT_BASE_SECONDS * (2**exponent), LOCKOUT_MAX_SECONDS)
            state.locked_until = now + duration
            return duration

    def record_success(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)

    def clear(self) -> None:
        """Test-only: wipes all state. Not called by the app itself -- see
        app/tests/conftest.py's autouse per-test reset."""
        with self._lock:
            self._state.clear()

    def _prune(self, now: float) -> None:
        stale_keys = [
            key
            for key, state in self._state.items()
            if state.locked_until < now and (now - state.last_failure_at) > STALE_ENTRY_SECONDS
        ]
        for key in stale_keys:
            del self._state[key]


account_throttle = LoginThrottle(MAX_ACCOUNT_FAILURES_BEFORE_LOCK)
# Deliberately never has record_success() called on it (see auth.py's
# login()): if it did, an attacker spraying attempts across many accounts
# from one IP could reset the shared IP counter just by successfully
# logging into any one account they already know the credentials for
# (e.g. their own, if this is an insider threat) and keep going. The
# per-account counter is fine to clear on success -- a correct login IS
# proof that account's owner is back in control.
ip_throttle = LoginThrottle(MAX_IP_FAILURES_BEFORE_LOCK)


def reset_all() -> None:
    """Test-only: see app/tests/conftest.py's autouse per-test reset. Not
    called by the app itself."""
    account_throttle.clear()
    ip_throttle.clear()


def get_client_ip(request) -> str:
    """Real client IP as seen through a reverse proxy. Caddy's
    reverse_proxy directive appends the immediate client's IP to
    X-Forwarded-For automatically (see the repo-root Caddyfile) -- with
    exactly one proxy hop in front of this service, that header holds
    exactly the browser's IP, so the first (only) entry is trusted as-is.
    Falls back to the ASGI-reported connecting socket when the header is
    absent (local dev with no proxy in front, or a direct request).
    NEVER trust this for anything beyond throttling -- it's operator-
    controlled input from the network path, not an authenticated fact.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

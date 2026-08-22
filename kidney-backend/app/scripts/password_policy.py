# app/scripts/password_policy.py
"""Password strength policy for operator-provisioned doctor accounts (B10 /
Phase 3.3 of FINALIZATION-PLAN.md). Used by app/scripts/create_doctor.py --
its own module, not folded into that script, so it's unit-testable without
a database.

Not a full breach-corpus check (a real "have I been pwned"-style lookup
needs either a network call this offline provisioning script shouldn't
depend on, or bundling a multi-megabyte wordlist for a handful of accounts
a hospital will ever provision) -- this catches the passwords an attacker
tries first: the ~150 most common real-world passwords from public
breach-frequency analyses, plus a handful of guessable patterns specific to
this app's context (predictable words, sequential digits, near-single-
character strings).
"""

MIN_PASSWORD_LENGTH = 12

# Drawn from the intersection of several public most-common-password
# analyses (RockYou-derived lists, annual "worst passwords" roundups) --
# the passwords that show up first in any real credential-stuffing attempt,
# not an exhaustive breach corpus. Lowercase; checked case-insensitively.
COMMON_PASSWORDS = frozenset(
    {
        "password", "123456", "12345678", "123456789", "1234567890",
        "12345", "1234567", "1234", "111111", "000000", "121212",
        "123123", "1q2w3e4r", "1qaz2wsx", "qazwsx", "qwerty", "qwerty123",
        "qwertyuiop", "asdfghjkl", "zxcvbnm", "letmein", "letme1n",
        "welcome", "welcome1", "welcome123", "admin", "administrator",
        "root", "toor", "changeme", "change123", "changeme123",
        "password1", "password123", "passw0rd", "p@ssword", "p@ssw0rd",
        "iloveyou", "iloveyou1", "monkey", "dragon", "master", "sunshine",
        "sunshine1", "princess", "football", "baseball", "basketball",
        "shadow", "superman", "batman", "trustno1", "hunter2", "abc123",
        "abcd1234", "starwars", "whatever", "freedom", "ninja", "mustang",
        "access", "flower", "hottie", "loveme", "jesus1", "michael",
        "jennifer", "michelle", "charlie", "computer", "internet",
        "login", "logmein", "pass1234", "test1234", "temp1234",
        "hospital", "hospital123", "doctor", "doctor123", "kidney",
        "kidney123", "patient123", "medical123", "clinic123",
        "Password1", "Password123", "P@ssw0rd", "P@ssword1", "Welcome1",
        "Admin123", "Qwerty123",
    }
)

# Fixed substrings that make a password guessable regardless of case,
# digits, or punctuation tacked onto them (e.g. "MyHospital2026!" still
# contains "hospital"). Deliberately short and specific -- a longer list
# risks rejecting a genuinely strong passphrase over an incidental
# substring match.
GUESSABLE_SUBSTRINGS = ("password", "qwerty", "letmein", "admin", "hospital", "welcome")


def _is_sequential_digits(password: str) -> bool:
    if not password.isdigit() or len(password) < 4:
        return False
    ascending = all(
        int(b) - int(a) == 1 for a, b in zip(password, password[1:])
    )
    descending = all(
        int(a) - int(b) == 1 for a, b in zip(password, password[1:])
    )
    return ascending or descending


def validate_password_strength(password: str) -> list[str]:
    """Returns a list of human-readable problems (empty if the password is
    acceptable). Never raises -- the caller decides what to do with a
    non-empty list (app/scripts/create_doctor.py exits with the messages
    joined; a future caller might just log a warning)."""
    problems: list[str] = []

    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters long")

    normalized = password.lower()

    if normalized in COMMON_PASSWORDS:
        problems.append(
            "is one of the most common passwords found in real-world credential "
            "breaches -- an attacker tries these first"
        )
    else:
        hit = next((s for s in GUESSABLE_SUBSTRINGS if s in normalized), None)
        if hit is not None:
            problems.append(f"contains the easily-guessed word {hit!r}")

    if len(set(password)) <= 2:
        problems.append("is (almost) a single repeated character")

    if _is_sequential_digits(password):
        problems.append("is a sequential run of digits (e.g. 123456...)")

    return problems

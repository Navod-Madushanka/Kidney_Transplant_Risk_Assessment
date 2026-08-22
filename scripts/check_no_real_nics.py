#!/usr/bin/env python3
"""CI guard against a real Sri Lankan NIC (national identity card number)
landing in tracked source (B8, FINALIZATION-PLAN.md Phase 3.4).

Background: a real patient's name ("Rev.S.Amarasinghe Thero") and real NIC
("198723456789") ended up copy-pasted into several test files and OCR
fixtures as "realistic-sounding" sample data. All of it has been replaced
with synthetic values (see PII_ALLOWLIST_PREFIXES below) -- this script is
the regression guard against it happening again, run in CI on every push
and PR (see .github/workflows/pii-scan.yml).

What this can and can't prove:
- CAN catch: any NIC-shaped literal (old format: 9 digits + V/X; new
  format: 12 digits) that doesn't start with one of the recognized
  synthetic prefixes below, appearing anywhere in a tracked source file.
- CANNOT catch: a real NIC that happens to start with one of those
  prefixes (vanishingly unlikely given how NICs are issued, but not
  impossible), or PII that isn't NIC-shaped at all (a real name on its own
  triggers nothing here -- there is no reliable way to grep for "is this a
  real person's name"). This is a lightweight regression guard for the
  specific pattern that already caused a real incident, not a general PII
  scanner. Use judgment, not just this script, when adding new test data
  that resembles a real person's records.

Scope: every git-tracked .py/.js/.jsx/.json file in the repo (uses
`git ls-files` so it automatically respects .gitignore -- the real,
gitignored lab-report images under kidney-backend/uploads/ are never
scanned or touched by this). Old-format NICs (9 digits + a single V/X
suffix) are checked anywhere in a matching file, since that shape rarely
collides with anything else (a hash, UUID, or timestamp doesn't end in
exactly one bare V/X after exactly 9 digits). New-format NICs (12 bare
digits) are checked only when "nic" (case-insensitive) appears elsewhere
on the same line, since a bare 12-digit run alone collides too often with
UUID segments, large integers, and timestamps to be a useful signal on its
own.
"""
import re
import subprocess
import sys

# Prefixes an NIC-shaped literal is allowed to start with -- deliberately
# one digit shorter than the full 9 (old format) or 12 (new format) digits
# each covers, so a *family* of values sharing that prefix (…001, …002, …)
# is allowlisted in one rule rather than needing a new entry per value. New
# test data should use "20000000" (12-digit) or "00000000" (9-digit + V/X)
# -- everything else here is a pre-existing convention from before this
# check existed, kept working rather than churned for its own sake.
PII_ALLOWLIST_PREFIXES = (
    "20000000",  # this pass's synthetic new-format prefix
    "00000000",  # this pass's synthetic old-format prefix
    "80000000",  # pre-existing: kidney-backend/app/tests/integration/test_pairs.py
    "90000000",  # pre-existing: same file, donor side of the same pairs
    "91234567",  # pre-existing: schemas/_validators.py's docstring example,
    # and a handful of tests that predate this check
)

OLD_FORMAT = re.compile(r"\b(\d{9})[VvXx]\b")
NEW_FORMAT = re.compile(r"\b(\d{12})\b")

SCANNED_SUFFIXES = (".py", ".js", ".jsx", ".json")


def _is_allowlisted(digits: str) -> bool:
    return any(digits.startswith(prefix) for prefix in PII_ALLOWLIST_PREFIXES)


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return [
        line for line in result.stdout.splitlines() if line.endswith(SCANNED_SUFFIXES)
    ]


def scan() -> list[str]:
    violations = []
    for path in _tracked_files():
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, OSError):
            continue

        for line_no, line in enumerate(lines, start=1):
            for match in OLD_FORMAT.finditer(line):
                if not _is_allowlisted(match.group(1)):
                    violations.append(
                        f"{path}:{line_no}: NIC-shaped literal {match.group(0)!r} "
                        "is not in the synthetic-data allowlist"
                    )

            if "nic" in line.lower():
                for match in NEW_FORMAT.finditer(line):
                    if not _is_allowlisted(match.group(1)):
                        violations.append(
                            f"{path}:{line_no}: NIC-shaped literal {match.group(0)!r} "
                            "is not in the synthetic-data allowlist"
                        )
    return violations


def main() -> int:
    violations = scan()
    if violations:
        print("Found NIC-shaped literals outside the synthetic-data allowlist:\n")
        for v in violations:
            print(f"  {v}")
        print(
            "\nIf this is real synthetic test data, use a value starting with "
            "'200000000' (12-digit) or '000000000' (9-digit + V/X), or add a new "
            "prefix to PII_ALLOWLIST_PREFIXES in scripts/check_no_real_nics.py with "
            "a comment explaining it. If this is a real person's NIC, remove it --"
            " see FINALIZATION-PLAN.md's B8 for why this check exists."
        )
        return 1

    print("No NIC-shaped literals found outside the synthetic-data allowlist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

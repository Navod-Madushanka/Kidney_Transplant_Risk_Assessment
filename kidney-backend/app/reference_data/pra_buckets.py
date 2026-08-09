# app/reference_data/pra_buckets.py
"""
PRA (%) buckets for Step 4. PRA here is calculated the same way as the
existing cPRA service (population-based), just re-bucketed per the new
spec's thresholds rather than the old pass/fail-only cPRA output.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PRABucket:
    name: str
    min_percent: float
    max_percent: float


# Boundaries are exact multiples of 30/60, not `.999`/`.001` epsilon values
# -- pra_bucket_service._bucket_for_percent compares with proper half-open
# interval logic (< / <=), so there's no gap between adjacent buckets for a
# value to fall through. The top bucket's max_percent is unbounded
# (review #2 bug 17: a fixed 100.0 ceiling meant any value that could ever
# exceed it -- impossible for a percentage, but the fallback-to-top-bucket
# behavior below was still the wrong direction in principle) -- see
# _bucket_for_percent's own docstring for the fix this replaced.
PRA_BUCKETS: list[PRABucket] = [
    PRABucket(name="<30%", min_percent=0.0, max_percent=30.0),
    PRABucket(name="30-60%", min_percent=30.0, max_percent=60.0),
    PRABucket(name=">60%", min_percent=60.0, max_percent=float("inf")),
]

# Clinical high-sensitisation threshold — anything strictly above this sets
# PRABucketResult.is_halted, but that field is informational only and does
# NOT reject the pairing (see pra_bucket_service.py's module docstring for
# why: cPRA is population-level, not pair-specific).
MAX_ACCEPTABLE_PRA_PERCENT = 60.0

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


PRA_BUCKETS: list[PRABucket] = [
    PRABucket(name="<30%", min_percent=0.0, max_percent=29.999),
    PRABucket(name="30-60%", min_percent=30.0, max_percent=60.0),
    PRABucket(name=">60%", min_percent=60.001, max_percent=100.0),
]

# Clinical high-sensitisation threshold — anything strictly above this sets
# PRABucketResult.is_halted, but that field is informational only and does
# NOT reject the pairing (see pra_bucket_service.py's module docstring for
# why: cPRA is population-level, not pair-specific).
MAX_ACCEPTABLE_PRA_PERCENT = 60.0

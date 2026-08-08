# app/services/pra_bucket_service.py
"""
Step 4 of the sequential compatibility pipeline: bucket the calculated cPRA
percentage per app/reference_data/pra_buckets.py. PRA itself is still
calculated by the existing cpra_service.py (population-based, unchanged) —
this only re-buckets that output against the new spec's three ranges
instead of treating cPRA as pass/fail-only.

PRABucketResult.is_halted does NOT halt the pipeline — match_pipeline.py
never branches on it. It briefly did (cPRA > MAX_ACCEPTABLE_PRA_PERCENT
rejected the pairing outright), reverted 2026-08-08: cPRA measures how hard
a patient is to match against the *population*, not whether this specific
donor is compatible, so using it as a reject gate meant the more sensitised
a patient was, the more certainly the system refused the one compatible
donor they'd actually found. Steps 5 (DSA) and 6 (crossmatch) are the real
pair-specific gates for sensitisation-related risk. The field is kept
(rather than removed) as a simple "exceeds the >60% clinical threshold"
signal for display/reference — treat it as informational only, never as a
reason to stop the pipeline.

When there isn't enough population data yet to calculate a cPRA
(CPRAResult.has_sufficient_data is False), has_sufficient_data=False is
preserved so Step 7's final classification can correctly decline to produce
a risk level rather than silently guessing one.
"""
from dataclasses import dataclass
from typing import Optional

from app.reference_data.pra_buckets import MAX_ACCEPTABLE_PRA_PERCENT, PRA_BUCKETS
from app.services.cpra_service import CPRAResult


@dataclass
class PRABucketResult:
    bucket_name: Optional[str]
    percent: Optional[float]
    is_halted: bool
    has_sufficient_data: bool


def calculate_pra_bucket(cpra_result: CPRAResult) -> PRABucketResult:
    if not cpra_result.has_sufficient_data:
        return PRABucketResult(
            bucket_name=None,
            percent=None,
            is_halted=False,
            has_sufficient_data=False,
        )

    percent = cpra_result.cpra_percentage
    bucket_name = _bucket_for_percent(percent)
    is_halted = percent > MAX_ACCEPTABLE_PRA_PERCENT

    return PRABucketResult(
        bucket_name=bucket_name,
        percent=percent,
        is_halted=is_halted,
        has_sufficient_data=True,
    )


def _bucket_for_percent(percent: float) -> str:
    for bucket in PRA_BUCKETS:
        if bucket.min_percent <= percent <= bucket.max_percent:
            return bucket.name
    # Values above 100 shouldn't occur, but fall back to the top bucket
    # rather than raising if they somehow do.
    return PRA_BUCKETS[-1].name

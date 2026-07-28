# app/reference_data/mismatch_buckets.py
"""
HLA mismatch count buckets for Step 3 of the sequential evaluation.
Only A, B, and DRB1 loci count toward this total (per current spec) —
unlike the older weighted hla_scoring_service which used all loci.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MismatchBucket:
    name: str
    min_count: int
    max_count: int


MISMATCH_BUCKETS: list[MismatchBucket] = [
    MismatchBucket(name="0 mismatches", min_count=0, max_count=0),
    MismatchBucket(name="<3 mismatches", min_count=1, max_count=2),
    MismatchBucket(name="3-6 mismatches", min_count=3, max_count=6),
]

# Anything above this is an automatic reject at Step 3.
MAX_ACCEPTABLE_MISMATCHES = 6

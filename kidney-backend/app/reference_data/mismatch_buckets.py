# app/reference_data/mismatch_buckets.py
"""
HLA mismatch count buckets for Step 3 of the sequential evaluation.
Only A, B, and DRB1 loci count toward this total (per current spec) —
unlike the older weighted hla_scoring_service which used all loci.

Bump MISMATCH_BUCKETS_VERSION any time the bucket boundaries below change,
so a report's stamped reference_versions (see MatchReport.reference_versions,
app/reference_data/versions.py) keeps meaning exactly what it meant when
that report was generated.
"""

from dataclasses import dataclass

MISMATCH_BUCKETS_VERSION = "project-spec-v1"


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

# T7: "<3 mismatches" is a stored value -- MatchReport.mismatch_result JSONB
# on every persisted report, and a lookup key in risk_classification.py's
# MISMATCH_BUCKET_POINTS -- so it can't be renamed without a migration. But
# displayed as-is it reads as if it also covers 0 (which has its own bucket
# right above it) -- a doctor could misread this bucket as "fewer than 3"
# rather than "1 or 2". This is a *display* label only; bucket.name stays
# the stored/lookup value everywhere else.
MISMATCH_BUCKET_DISPLAY_LABELS: dict[str, str] = {
    "0 mismatches": "0 mismatches",
    "<3 mismatches": "1-2 mismatches",
    "3-6 mismatches": "3-6 mismatches",
}


def mismatch_bucket_display_label(bucket_name: str) -> str:
    return MISMATCH_BUCKET_DISPLAY_LABELS.get(bucket_name, bucket_name)

# The gate rejects once total_mismatches reaches this count (inclusive),
# not only above it -- with exactly two alleles per locus across the three
# counted loci (A/B/DRB1), 6 is also the maximum value the count can ever
# reach, so a strict "reject above 6" rule would never actually fire. A full
# 6/6 mismatch (every donor allele absent from the patient at every counted
# locus) is the real, reachable reject case.
MAX_ACCEPTABLE_MISMATCHES = 6

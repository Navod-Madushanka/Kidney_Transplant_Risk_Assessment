# app/services/hla_mismatch_service.py
"""
Step 3 of the sequential compatibility pipeline: count HLA mismatches
between patient and donor, restricted to the A, B, and DRB1 loci only (per
the doctors' feedback and app/reference_data/mismatch_buckets.py — see the
project's development roadmap, Phase 3). This is deliberately separate from
the older calculate_hla_risk_score in hla_scoring_service.py, which weighs
mismatches across all 9 HLA loci and is kept around only as a legacy
reference score alongside the new step-based result, not as part of the
new gate sequence.

A missing locus (patient or donor typing not yet entered for A/B/DRB1) is
treated as contributing the *maximum* possible mismatches for that locus
rather than zero. This is a deliberate conservative choice: incomplete data
should never make a pairing look more compatible than it might actually be.
A set-difference against an empty allele list is always empty, so a missing
side is special-cased before that computation runs rather than being allowed
to fall through it. MismatchResult.data_completeness reflects whether any
locus had to be scored this way, so callers (e.g. the Step 7 final risk
classification in match_pipeline.py) can refuse to present a risk level
built on incomplete typing data rather than showing a falsely favorable one.
"""
from dataclasses import dataclass, field

from app.reference_data.mismatch_buckets import MAX_ACCEPTABLE_MISMATCHES, MISMATCH_BUCKETS

MISMATCH_COUNTED_LOCI = ("A", "B", "DRB1")

# Each locus stores at most 2 alleles, so 2 is the worst case a single locus
# can contribute — used in place of a set-difference computation whenever
# one side's typing for that locus hasn't been entered at all.
MAX_MISMATCHES_PER_LOCUS = 2


@dataclass
class LocusMismatchDetail:
    locus: str
    patient_alleles: list[str]
    donor_alleles: list[str]
    unique_mismatches: int


@dataclass
class MismatchResult:
    total_mismatches: int
    bucket_name: str
    is_halted: bool
    data_completeness: bool = True
    locus_breakdown: list[LocusMismatchDetail] = field(default_factory=list)


def calculate_mismatch_result(
    patient_typing: dict[str, list[str]],
    donor_typing: dict[str, list[str]],
) -> MismatchResult:
    """patient_typing / donor_typing only need entries for
    MISMATCH_COUNTED_LOCI — callers should build these permissively (missing
    locus -> empty list), not via the strict all-9-loci dict getters in
    hla_typing_service.py. See build_partial_typing_dict() there.
    """
    locus_breakdown = []
    total_mismatches = 0
    data_completeness = True

    for locus in MISMATCH_COUNTED_LOCI:
        patient_alleles = patient_typing.get(locus, [])
        donor_alleles = donor_typing.get(locus, [])

        if not patient_alleles or not donor_alleles:
            # Typing hasn't been entered for this locus on at least one side
            # -- a set difference against an empty list is always empty, so
            # computing it here would silently score the pairing as a match.
            # Score the worst case instead and flag the result incomplete.
            unique_mismatches = MAX_MISMATCHES_PER_LOCUS
            data_completeness = False
        else:
            donor_allele_set = set(donor_alleles)
            patient_allele_set = set(patient_alleles)
            unique_mismatches = len(donor_allele_set - patient_allele_set)

        total_mismatches += unique_mismatches

        locus_breakdown.append(
            LocusMismatchDetail(
                locus=locus,
                patient_alleles=patient_alleles,
                donor_alleles=donor_alleles,
                unique_mismatches=unique_mismatches,
            )
        )

    bucket_name = _bucket_for_count(total_mismatches)
    # >= , not > : with exactly two alleles per locus across the three
    # counted loci, 6 is also the maximum value total_mismatches can ever
    # reach, so a strict `>` here made the reject path mathematically
    # unreachable. MAX_ACCEPTABLE_MISMATCHES is the first count that
    # rejects, not the last one that still passes -- see the comment on it
    # in mismatch_buckets.py.
    is_halted = total_mismatches >= MAX_ACCEPTABLE_MISMATCHES

    return MismatchResult(
        total_mismatches=total_mismatches,
        bucket_name=bucket_name,
        is_halted=is_halted,
        data_completeness=data_completeness,
        locus_breakdown=locus_breakdown,
    )


def _bucket_for_count(count: int) -> str:
    for bucket in MISMATCH_BUCKETS:
        if bucket.min_count <= count <= bucket.max_count:
            return bucket.name
    # Above the highest defined bucket (i.e. > MAX_ACCEPTABLE_MISMATCHES) —
    # still needs a display name even though this always halts Step 3.
    return f">{MAX_ACCEPTABLE_MISMATCHES} mismatches"

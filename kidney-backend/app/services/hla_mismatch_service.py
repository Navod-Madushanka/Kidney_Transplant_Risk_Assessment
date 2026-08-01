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
"""
from dataclasses import dataclass, field

from app.reference_data.mismatch_buckets import MAX_ACCEPTABLE_MISMATCHES, MISMATCH_BUCKETS

MISMATCH_COUNTED_LOCI = ("A", "B", "DRB1")


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

    for locus in MISMATCH_COUNTED_LOCI:
        patient_alleles = patient_typing.get(locus, [])
        donor_alleles = donor_typing.get(locus, [])

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
    is_halted = total_mismatches > MAX_ACCEPTABLE_MISMATCHES

    return MismatchResult(
        total_mismatches=total_mismatches,
        bucket_name=bucket_name,
        is_halted=is_halted,
        locus_breakdown=locus_breakdown,
    )


def _bucket_for_count(count: int) -> str:
    for bucket in MISMATCH_BUCKETS:
        if bucket.min_count <= count <= bucket.max_count:
            return bucket.name
    # Above the highest defined bucket (i.e. > MAX_ACCEPTABLE_MISMATCHES) —
    # still needs a display name even though this always halts Step 3.
    return f">{MAX_ACCEPTABLE_MISMATCHES} mismatches"

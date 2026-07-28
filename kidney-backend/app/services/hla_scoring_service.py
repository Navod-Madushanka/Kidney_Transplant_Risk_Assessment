# app/services/hla_scoring_service.py
from dataclasses import dataclass, field

from app.reference_data.hla_weights import HLA_LOCUS_WEIGHTS


@dataclass
class LocusResult:
    locus: str
    patient_alleles: list[str]
    donor_alleles: list[str]
    unique_mismatches: int
    weight: float
    points: float


@dataclass
class HLAScoringResult:
    total_score: float
    locus_breakdown: list[LocusResult] = field(default_factory=list)


def calculate_hla_risk_score(
    patient_typing: dict[str, list[str]],
    donor_typing: dict[str, list[str]],
) -> HLAScoringResult:
    locus_breakdown = []
    total_score = 0.0

    for locus, weight in HLA_LOCUS_WEIGHTS.items():
        patient_alleles = patient_typing[locus]
        donor_alleles = donor_typing[locus]

        donor_allele_set = set(donor_alleles)
        patient_allele_set = set(patient_alleles)
        mismatched_alleles = donor_allele_set - patient_allele_set
        unique_mismatches = len(mismatched_alleles)

        points = unique_mismatches * weight
        total_score += points

        locus_breakdown.append(
            LocusResult(
                locus=locus,
                patient_alleles=patient_alleles,
                donor_alleles=donor_alleles,
                unique_mismatches=unique_mismatches,
                weight=weight,
                points=points,
            )
        )

    return HLAScoringResult(total_score=total_score, locus_breakdown=locus_breakdown)

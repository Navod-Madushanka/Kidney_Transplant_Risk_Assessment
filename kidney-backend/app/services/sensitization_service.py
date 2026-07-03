# app/services/sensitization_service.py
from dataclasses import dataclass, field

from app.reference_data.sensitization_weights import (
    SENSITIZATION_CUTOFF_REDUCTION_FACTOR,
    SENSITIZATION_EVENT_WEIGHTS,
)


@dataclass
class SensitizationEventDetail:
    event_type: str
    points: float


@dataclass
class SensitizationResult:
    total_score: float
    event_breakdown: list[SensitizationEventDetail] = field(default_factory=list)
    adjusted_mfi_cutoff: float = 0.0


def calculate_sensitization_score(
    event_types: list[str],
    base_mfi_cutoff: float,
) -> SensitizationResult:
    event_breakdown = []
    total_score = 0.0

    for event_type in event_types:
        weight = SENSITIZATION_EVENT_WEIGHTS[event_type]
        total_score += weight
        event_breakdown.append(
            SensitizationEventDetail(event_type=event_type, points=weight)
        )

    adjusted_mfi_cutoff = base_mfi_cutoff - (
        total_score * SENSITIZATION_CUTOFF_REDUCTION_FACTOR
    )

    return SensitizationResult(
        total_score=total_score,
        event_breakdown=event_breakdown,
        adjusted_mfi_cutoff=adjusted_mfi_cutoff,
    )
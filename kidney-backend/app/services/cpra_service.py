# app/services/cpra_service.py
from dataclasses import dataclass
from typing import Optional

from app.reference_data.cpra_settings import MINIMUM_POPULATION_SAMPLE_SIZE


@dataclass
class CPRAResult:
    cpra_percentage: Optional[float]
    sample_size: int
    has_sufficient_data: bool
    message: str


def calculate_population_antigen_frequencies(
    population_profiles: list[list[str]],
) -> dict[str, float]:
    sample_size = len(population_profiles)
    antigen_counts: dict[str, int] = {}

    for profile in population_profiles:
        for antigen in set(profile):
            antigen_counts[antigen] = antigen_counts.get(antigen, 0) + 1

    return {
        antigen: count / sample_size for antigen, count in antigen_counts.items()
    }


def calculate_cpra(
    sensitized_antigens: list[str],
    population_profiles: list[list[str]],
) -> CPRAResult:
    sample_size = len(population_profiles)

    if sample_size < MINIMUM_POPULATION_SAMPLE_SIZE:
        return CPRAResult(
            cpra_percentage=None,
            sample_size=sample_size,
            has_sufficient_data=False,
            message="Not enough data yet to calculate cPRA",
        )

    antigen_frequencies = calculate_population_antigen_frequencies(population_profiles)

    combined_frequency = 0.0
    for antigen in sensitized_antigens:
        frequency = antigen_frequencies.get(antigen, 0.0)
        combined_frequency = (
            combined_frequency + frequency - (combined_frequency * frequency)
        )

    return CPRAResult(
        cpra_percentage=combined_frequency * 100,
        sample_size=sample_size,
        has_sufficient_data=True,
        message="OK",
    )
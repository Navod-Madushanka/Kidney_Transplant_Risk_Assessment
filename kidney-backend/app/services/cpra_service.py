# app/services/cpra_service.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class CPRAResult:
    cpra_percentage: Optional[float]
    sample_size: int
    has_sufficient_data: bool
    message: str
    reference_table_version: str
    source_citation: str


def calculate_cpra(
    sensitized_antigens: list[str],
    antigen_frequencies: dict[str, float],
    reference_sample_size: int,
    reference_table_version: str,
    source_citation: str,
) -> CPRAResult:
    combined_frequency = 0.0
    matched = 0
    for antigen in sensitized_antigens:
        frequency = antigen_frequencies.get(antigen, 0.0)
        if frequency > 0.0:
            matched += 1
        # Union-probability combination -- assumes each sensitized antigen is
        # an independent event. Real HLA loci are in linkage disequilibrium
        # (haplotypes travel together), so this is a disclosed approximation,
        # not a fix -- see the "Known limitation" section of
        # app/reference_data/hla_antigen_frequencies.py's module docstring.
        combined_frequency = (
            combined_frequency + frequency - (combined_frequency * frequency)
        )

    total = len(sensitized_antigens)
    message = (
        "OK"
        if total == 0
        else f"{matched} of {total} sensitized antigens matched the reference frequency table"
    )

    return CPRAResult(
        cpra_percentage=combined_frequency * 100,
        sample_size=reference_sample_size,
        has_sufficient_data=True,
        message=message,
        reference_table_version=reference_table_version,
        source_citation=source_citation,
    )

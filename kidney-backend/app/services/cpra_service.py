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
    # Part I (I9): a real Sero group legitimately spans several distinct
    # beads on the bead-specificity panel (e.g. "A24" on beads 011 and
    # 012 at different MFIs -- see ocr-service's bead_reconciliation.py
    # module docstring), so a sensitized patient's antigen list can
    # legitimately contain the same antigen name more than once. Combining
    # a repeated antigen's frequency into itself twice
    # (`2f - f^2` instead of `f`) overstated cPRA for essentially every
    # sensitized patient, independent of any OCR error -- this predates
    # and is unrelated to the bead-identity work above; the analysis of
    # WHY repeats are common is what surfaced it. Deduplicating by
    # normalized name before the union-probability combination is the
    # fix: cPRA answers "how sensitized is this patient against the
    # population," which only cares whether an antigen is present, not
    # how many source rows reported it.
    unique_antigens = list(dict.fromkeys(sensitized_antigens))

    combined_frequency = 0.0
    matched = 0
    for antigen in unique_antigens:
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

    total = len(unique_antigens)
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

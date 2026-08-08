# app/services/dsa_service.py
from dataclasses import dataclass, field

from app.reference_data.dsa_threshold import DSA_HALTING_SEVERITY, DSA_SEVERITY_BANDS

# cPRA sensitization screen only (Step 4) — a population-level question,
# deliberately kept separate from the Step 5 DSA severity bands in
# app/reference_data/dsa_threshold.py. See that module's docstring.
DEFAULT_MFI_CUTOFF = 2000.0


@dataclass
class PatientAntibody:
    antigen: str
    mfi: float


@dataclass
class DSAMatch:
    antigen: str
    mfi: float
    severity: str
    warning_message: str


@dataclass
class DSAResult:
    is_halted: bool
    requires_review: bool
    matches: list[DSAMatch] = field(default_factory=list)
    # The floor/band boundaries in force when this result was computed, so a
    # stored report keeps its clinical meaning even if the reference data
    # module's numbers change later.
    floor: float = 0.0
    bands: list[dict] = field(default_factory=list)


def _grade(mfi: float) -> str:
    for band in DSA_SEVERITY_BANDS:
        if band.min_mfi <= mfi <= band.max_mfi:
            return band.name
    # Above the top band's nominal max (shouldn't happen since it's
    # unbounded) — fall back to the most severe band rather than raising.
    return DSA_SEVERITY_BANDS[-1].name


def check_dsa(
    patient_antibodies: list[PatientAntibody],
    donor_hla_antigens: list[str],
    floor: float = DSA_SEVERITY_BANDS[0].min_mfi,
) -> DSAResult:
    flagged_antibodies = [
        antibody for antibody in patient_antibodies if antibody.mfi >= floor
    ]

    matches = []
    for antibody in flagged_antibodies:
        if antibody.antigen in donor_hla_antigens:
            severity = _grade(antibody.mfi)
            if severity == DSA_HALTING_SEVERITY:
                warning_message = (
                    "CRITICAL WARNING: Donor-Specific Antibody (DSA) detected. "
                    f"Patient has a {severity} antibody against donor HLA "
                    f"{antibody.antigen} with an MFI of {antibody.mfi}. "
                    "Process halted due to very high risk of rejection."
                )
            else:
                warning_message = (
                    f"Donor-Specific Antibody (DSA) detected against donor HLA "
                    f"{antibody.antigen} with an MFI of {antibody.mfi}, graded "
                    f"{severity}. Not halted automatically, but flagged for "
                    "desensitization protocol review."
                )
            matches.append(
                DSAMatch(
                    antigen=antibody.antigen,
                    mfi=antibody.mfi,
                    severity=severity,
                    warning_message=warning_message,
                )
            )

    is_halted = any(match.severity == DSA_HALTING_SEVERITY for match in matches)
    requires_review = any(match.severity != DSA_HALTING_SEVERITY for match in matches)

    return DSAResult(
        is_halted=is_halted,
        requires_review=requires_review,
        matches=matches,
        floor=floor,
        # max_mfi=None (not inf) for the open-ended top band — this gets
        # persisted as JSONB on the report, and JSON has no Infinity literal.
        bands=[
            {
                "name": band.name,
                "min_mfi": band.min_mfi,
                "max_mfi": band.max_mfi if band.max_mfi != float("inf") else None,
            }
            for band in DSA_SEVERITY_BANDS
        ],
    )

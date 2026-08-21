# app/services/dsa_service.py
from dataclasses import dataclass, field

from app.reference_data.dsa_threshold import DSA_HALTING_SEVERITY, DSA_SEVERITY_BANDS

# cPRA sensitization screen only (Step 4) — a population-level question,
# deliberately kept separate from the Step 5 DSA severity bands in
# app/reference_data/dsa_threshold.py. See that module's docstring.
DEFAULT_MFI_CUTOFF = 2000.0

# An allele-level HLA designation ("B*44:02") uses a completely different
# naming scheme from the serological designations donor_hla_antigens is
# built from (hla_antigen_designation() in hla_typing_service.py only ever
# produces bare "B44"-style strings) -- exact-string matching below can
# never match one, no matter what the donor's real typing is.
# schemas/antibody_profile.py now rejects this shape at entry, but this is a
# second, independent check: it also catches whatever was saved before that
# validator existed, since a patient's stored antibody profile can predate
# this fix. Any flagged antibody in this shape is surfaced as a review flag
# rather than silently producing no match -- see UnmappedAntibody below.
_ALLELE_LEVEL_CHARS = ("*", ":")


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
class UnmappedAntibody:
    antigen: str
    mfi: float
    reason: str


@dataclass
class DSAResult:
    is_halted: bool
    requires_review: bool
    matches: list[DSAMatch] = field(default_factory=list)
    # Flagged antibodies (mfi >= floor) whose antigen string is structurally
    # unmatchable against any donor typing, regardless of what the donor's
    # real HLA looks like -- e.g. entered allele-level. Never silently
    # dropped: requires_review is set whenever this is non-empty, same as a
    # real weak/moderate DSA match, so it surfaces on the report instead of
    # looking identical to "no antibody against this donor".
    unmapped_antibodies: list[UnmappedAntibody] = field(default_factory=list)
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
    unmapped_antibodies = []
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
        elif any(char in antibody.antigen for char in _ALLELE_LEVEL_CHARS):
            unmapped_antibodies.append(
                UnmappedAntibody(
                    antigen=antibody.antigen,
                    mfi=antibody.mfi,
                    reason=(
                        f"'{antibody.antigen}' looks like an allele-level typing, not a "
                        "serological designation -- it cannot be matched against donor "
                        "HLA typing in this format."
                    ),
                )
            )

    is_halted = any(match.severity == DSA_HALTING_SEVERITY for match in matches)
    requires_review = (
        any(match.severity != DSA_HALTING_SEVERITY for match in matches)
        or bool(unmapped_antibodies)
    )

    return DSAResult(
        is_halted=is_halted,
        requires_review=requires_review,
        matches=matches,
        unmapped_antibodies=unmapped_antibodies,
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

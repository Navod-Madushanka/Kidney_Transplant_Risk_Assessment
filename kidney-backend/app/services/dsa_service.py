# app/services/dsa_service.py
from dataclasses import dataclass, field

from app.reference_data.dsa_threshold import DSA_HALTING_SEVERITY, DSA_SEVERITY_BANDS
from app.services.hla_typing_service import locus_for_antigen_designation

# cPRA sensitisation screen only (Step 4) — a population-level question,
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
    # Flagged antibodies (mfi >= floor) whose target locus is a recognized
    # serological designation, but the donor has NO typing on record for
    # that locus at all -- e.g. an anti-DQ antibody when the donor's DQB1
    # typing was never entered. Unlike a real negative (donor typed at that
    # locus, confirmed not to carry the antigen), this pairing was never
    # actually screened for this antibody -- surfaced here instead of
    # silently looking identical to a clean screen, same rationale as
    # MismatchResult.data_completeness in hla_mismatch_service.py.
    # Only populated when donor_typed_loci is passed to check_dsa.
    untyped_locus_antibodies: list[UnmappedAntibody] = field(default_factory=list)
    # The donor loci that actually had typing on record when this result was
    # computed, i.e. what was actually screened against -- empty if the
    # caller didn't pass donor_typed_loci (screening completeness unknown).
    screened_loci: list[str] = field(default_factory=list)
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
    donor_typed_loci: set[str] | None = None,
    floor: float = DSA_SEVERITY_BANDS[0].min_mfi,
) -> DSAResult:
    """donor_typed_loci is the set of HLA typing loci the donor actually has
    entries for (e.g. {"A", "B", "DRB1"}) -- pass it whenever available so an
    antibody against a locus the donor was never typed for is flagged rather
    than silently treated as a confirmed negative (a set-difference /
    membership test against an absent locus can never match, no matter what
    the donor's real HLA looks like). Left as None only for callers that
    can't supply it; the untyped-locus check is skipped in that case rather
    than guessing.
    """
    flagged_antibodies = [
        antibody for antibody in patient_antibodies if antibody.mfi >= floor
    ]

    matches = []
    unmapped_antibodies = []
    untyped_locus_antibodies = []
    for antibody in flagged_antibodies:
        if antibody.antigen in donor_hla_antigens:
            severity = _grade(antibody.mfi)
            if severity == DSA_HALTING_SEVERITY:
                warning_message = (
                    "CRITICAL WARNING: Donor-Specific Antibody (DSA) detected. "
                    f"Recipient has a {severity} antibody against donor HLA "
                    f"{antibody.antigen} with an MFI of {antibody.mfi}. "
                    "Process halted due to very high risk of rejection."
                )
            else:
                warning_message = (
                    f"Donor-Specific Antibody (DSA) detected against donor HLA "
                    f"{antibody.antigen} with an MFI of {antibody.mfi}, graded "
                    f"{severity}. Not halted automatically, but flagged for "
                    "desensitisation protocol review."
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
        elif donor_typed_loci is not None:
            locus = locus_for_antigen_designation(antibody.antigen)
            if locus is not None and locus not in donor_typed_loci:
                untyped_locus_antibodies.append(
                    UnmappedAntibody(
                        antigen=antibody.antigen,
                        mfi=antibody.mfi,
                        reason=(
                            f"Donor has no {locus} typing on record -- this antibody "
                            "could not be screened against the donor's actual HLA."
                        ),
                    )
                )

    is_halted = any(match.severity == DSA_HALTING_SEVERITY for match in matches)
    requires_review = (
        any(match.severity != DSA_HALTING_SEVERITY for match in matches)
        or bool(unmapped_antibodies)
        or bool(untyped_locus_antibodies)
    )

    return DSAResult(
        is_halted=is_halted,
        requires_review=requires_review,
        matches=matches,
        unmapped_antibodies=unmapped_antibodies,
        untyped_locus_antibodies=untyped_locus_antibodies,
        screened_loci=sorted(donor_typed_loci) if donor_typed_loci is not None else [],
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

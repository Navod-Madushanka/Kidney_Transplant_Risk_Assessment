# app/services/dsa_service.py
from dataclasses import dataclass, field

DEFAULT_MFI_CUTOFF = 2000.0


@dataclass
class PatientAntibody:
    antigen: str
    mfi: float


@dataclass
class DSAMatch:
    antigen: str
    mfi: float
    cutoff: float
    warning_message: str


@dataclass
class DSAResult:
    is_halted: bool
    matches: list[DSAMatch] = field(default_factory=list)


def check_dsa(
    patient_antibodies: list[PatientAntibody],
    donor_hla_antigens: list[str],
    mfi_cutoff_value: float = DEFAULT_MFI_CUTOFF,
) -> DSAResult:
    high_mfi_antibodies = [
        antibody for antibody in patient_antibodies if antibody.mfi > mfi_cutoff_value
    ]

    matches = []
    for antibody in high_mfi_antibodies:
        if antibody.antigen in donor_hla_antigens:
            warning_message = (
                "CRITICAL WARNING: Donor-Specific Antibody (DSA) detected. "
                f"Patient has an antibody against donor HLA {antibody.antigen} "
                f"with an MFI of {antibody.mfi}, exceeding the threshold of "
                f"{mfi_cutoff_value}. Process halted due to very high risk of rejection."
            )
            matches.append(
                DSAMatch(
                    antigen=antibody.antigen,
                    mfi=antibody.mfi,
                    cutoff=mfi_cutoff_value,
                    warning_message=warning_message,
                )
            )

    return DSAResult(is_halted=len(matches) > 0, matches=matches)
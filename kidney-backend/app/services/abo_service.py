# app/services/abo_service.py
from dataclasses import dataclass

from app.reference_data.abo_compatibility import ABO_COMPATIBILITY


@dataclass
class ABOResult:
    is_compatible: bool
    recipient_type: str
    donor_type: str


def check_abo_compatibility(recipient_type: str, donor_type: str) -> ABOResult:
    compatible_donor_types = ABO_COMPATIBILITY[recipient_type]
    is_compatible = donor_type in compatible_donor_types

    return ABOResult(
        is_compatible=is_compatible,
        recipient_type=recipient_type,
        donor_type=donor_type,
    )

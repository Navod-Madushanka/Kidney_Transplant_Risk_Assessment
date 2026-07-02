# app/tests/unit/test_abo_service.py
import pytest

from app.services.abo_service import check_abo_compatibility


@pytest.mark.parametrize(
    "recipient_type,donor_type,expected",
    [
        # Recipient O — universal donor, only compatible with O
        ("O", "O", True),
        ("O", "A", False),
        ("O", "B", False),
        ("O", "AB", False),
        # Recipient A
        ("A", "A", True),
        ("A", "O", True),
        ("A", "B", False),
        ("A", "AB", False),
        # Recipient B
        ("B", "B", True),
        ("B", "O", True),
        ("B", "A", False),
        ("B", "AB", False),
        # Recipient AB — universal recipient, compatible with everything
        ("AB", "A", True),
        ("AB", "B", True),
        ("AB", "AB", True),
        ("AB", "O", True),
    ],
)
def test_abo_compatibility(recipient_type, donor_type, expected):
    result = check_abo_compatibility(recipient_type, donor_type)
    assert result.is_compatible == expected
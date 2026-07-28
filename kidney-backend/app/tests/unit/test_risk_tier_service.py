# app/tests/unit/test_risk_tier_service.py
import pytest

from app.services.risk_tier_service import get_risk_tier


@pytest.mark.parametrize(
    "score,expected_tier",
    [
        (0.0, "Low Risk"),
        (2.0, "Low Risk"),
        (2.25, "Moderate Risk"),
        (5.0, "Moderate Risk"),
        (5.25, "High-Moderate Risk"),
        (7.0, "High-Moderate Risk"),
        (7.25, "High Genetic Risk"),
        (10.0, "High Genetic Risk"),
    ],
)
def test_risk_tier_boundaries(score, expected_tier):
    assert get_risk_tier(score) == expected_tier


def test_score_below_zero_raises():
    with pytest.raises(ValueError):
        get_risk_tier(-1.0)

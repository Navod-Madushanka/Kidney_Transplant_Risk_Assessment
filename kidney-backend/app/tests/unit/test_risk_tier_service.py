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
        (7.25, "High Immunological Risk"),
        (10.0, "High Immunological Risk"),
        # B13 regression: these previously fell in the gap between adjacent
        # bands' independently-set min/max and raised ValueError, even
        # though a non-quarter locus weight is the only way to ever produce
        # them. Bands are now contiguous half-open intervals, so every score
        # in [0, 10] resolves to exactly one tier.
        (2.1, "Low Risk"),
        (5.1, "Moderate Risk"),
        (7.1, "High-Moderate Risk"),
    ],
)
def test_risk_tier_boundaries(score, expected_tier):
    assert get_risk_tier(score) == expected_tier


def test_score_below_zero_raises():
    with pytest.raises(ValueError):
        get_risk_tier(-1.0)


def test_score_above_max_raises():
    with pytest.raises(ValueError):
        get_risk_tier(10.01)

# app/services/risk_tier_service.py
from app.reference_data.risk_tiers import RISK_TIERS


def get_risk_tier(score: float) -> str:
    """Bands are half-open [min, max) except the last, which is inclusive at
    both ends -- see the contiguity assertion in risk_tiers.py. Using
    strict `<` against a tier's own max (rather than `<=`) is what keeps
    adjacent bands from double-matching at their shared boundary.
    """
    last = RISK_TIERS[-1]
    for tier in RISK_TIERS:
        if tier is last:
            if tier.min_score <= score <= tier.max_score:
                return tier.name
        elif tier.min_score <= score < tier.max_score:
            return tier.name

    raise ValueError(f"Score {score} does not fall within any defined risk tier")

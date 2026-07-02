# app/services/risk_tier_service.py
from app.reference_data.risk_tiers import RISK_TIERS


def get_risk_tier(score: float) -> str:
    for tier in RISK_TIERS:
        if tier.min_score <= score <= tier.max_score:
            return tier.name

    raise ValueError(f"Score {score} does not fall within any defined risk tier")
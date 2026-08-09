# app/reference_data/risk_tiers.py
"""
HLA risk score → clinical risk tier boundaries.
Source: project specification slide 10 -- see docs/clinical-basis.md for
the full rationale and what is/isn't externally citable about these numbers.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskTier:
    name: str
    min_score: float
    max_score: float


RISK_TIERS: list[RiskTier] = [
    RiskTier(name="Low Risk", min_score=0.0, max_score=2.0),
    RiskTier(name="Moderate Risk", min_score=2.25, max_score=5.0),
    RiskTier(name="High-Moderate Risk", min_score=5.25, max_score=7.0),
    RiskTier(name="High Genetic Risk", min_score=7.25, max_score=10.0),
]

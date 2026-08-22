# app/reference_data/risk_tiers.py
"""
HLA risk score → clinical risk tier boundaries.
Source: project specification slide 10 -- see docs/clinical-basis.md for
the full rationale and what is/isn't externally citable about these numbers.

Bands are contiguous half-open intervals: min_score <= score < max_score,
except the top band, which is inclusive at both ends. Every achievable score
is a multiple of 0.25 (every HLA_LOCUS_WEIGHTS weight -- app/reference_data/
hla_weights.py -- is itself a multiple of 0.25), and the spec's own written
boundaries (0-2, 2.25-5, 5.25-7, 7.25-10) already land on quarter-point
values, so closing the gaps between bands (2.0-2.25, 5.0-5.25, 7.0-7.25) at
the midpoint-free "next band's min" doesn't reclassify any score the spec's
own boundaries would produce -- it only removes dead space that a future
non-quarter locus weight could otherwise land a score in, which previously
raised ValueError out of get_risk_tier() (see risk_tier_service.py) instead
of returning a tier.

Bump RISK_TIERS_VERSION any time the band boundaries or names below change,
so a report's stamped reference_versions (see MatchReport.reference_versions,
app/reference_data/versions.py) keeps meaning exactly what it meant when
that report was generated.
"""

from dataclasses import dataclass

RISK_TIERS_VERSION = "project-spec-v1"


@dataclass(frozen=True)
class RiskTier:
    name: str
    min_score: float
    max_score: float


RISK_TIERS: list[RiskTier] = [
    RiskTier(name="Low Risk", min_score=0.0, max_score=2.25),
    RiskTier(name="Moderate Risk", min_score=2.25, max_score=5.25),
    RiskTier(name="High-Moderate Risk", min_score=5.25, max_score=7.25),
    RiskTier(name="High Immunological Risk", min_score=7.25, max_score=10.0),
]

# Startup assertion: bands must cover [0, top max] with no gap and no
# overlap -- i.e. each band's max must equal the next band's min exactly.
# Catches a future edit to RISK_TIERS that reopens the B13 gap bug instead
# of letting get_risk_tier() start silently raising ValueError again.
assert RISK_TIERS[0].min_score == 0.0, "RISK_TIERS must start at 0.0"
assert all(
    prev.max_score == nxt.min_score for prev, nxt in zip(RISK_TIERS, RISK_TIERS[1:])
), "RISK_TIERS has a gap or overlap -- each band's max must equal the next band's min"

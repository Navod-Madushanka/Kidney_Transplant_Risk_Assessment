# app/reference_data/risk_classification.py
"""
Step 7 final risk classification. Combines the bucket reached at Step 3
(HLA mismatches) and Step 4 (PRA) into a single score, then maps that
score to one of four risk levels.

Scoring (only reachable buckets counted — anything worse already
rejected the case before Step 7):
  Mismatch bucket:  "0 mismatches" -> 0 pts
                    "<3 mismatches" -> 1 pt
                    "3-6 mismatches" -> 2 pts
  PRA bucket:       "<30%" -> 0 pts
                    "30-60%" -> 1 pt

Total score -> risk level:
  0        -> Low Risk
  1        -> Low-Average Risk
  2        -> High-Average Risk
  3        -> High Risk
"""

MISMATCH_BUCKET_POINTS: dict[str, int] = {
    "0 mismatches": 0,
    "<3 mismatches": 1,
    "3-6 mismatches": 2,
}

PRA_BUCKET_POINTS: dict[str, int] = {
    "<30%": 0,
    "30-60%": 1,
}

SCORE_TO_RISK_LEVEL: dict[int, str] = {
    0: "Low Risk",
    1: "Low-Average Risk",
    2: "High-Average Risk",
    3: "High Risk",
}


def classify_risk(mismatch_bucket_name: str, pra_bucket_name: str) -> str:
    score = (
        MISMATCH_BUCKET_POINTS[mismatch_bucket_name]
        + PRA_BUCKET_POINTS[pra_bucket_name]
    )
    return SCORE_TO_RISK_LEVEL[score]
# app/reference_data/risk_classification.py
"""
Step 7 final risk classification. Combines the bucket reached at Step 3
(HLA mismatches) and Step 4 (cPRA) into a single score, then maps that
score to one of four risk levels.

Scoring (only buckets with a doctor-specified point value are counted):
  Mismatch bucket:  "0 mismatches" -> 0 pts
                    "<3 mismatches" -> 1 pt
                    "3-6 mismatches" -> 2 pts
  cPRA bucket:      "<30%" -> 0 pts
                    "30-60%" -> 1 pt
                    ">60%" -> no point value yet (see below)

Total score -> risk level:
  0        -> Low Risk
  1        -> Low-Average Risk
  2        -> High-Average Risk
  3        -> High Risk

CPRA_BUCKET_POINTS deliberately has no entry for ">60%": Step 4 used to
reject a pairing outright above 60% cPRA, so this function never had to
score that bucket. That gate was removed 2026-08-08 (cPRA is population-
level, not pair-specific — see match_pipeline.py's module docstring), which
means a ">60%" bucket can now reach here on a real, non-halted check. No
clinical point value for it has been specified by the doctors yet, so
classify_risk returns None for that combination rather than guessing one —
same "don't guess" precedent as insufficient cPRA population data or
incomplete HLA typing elsewhere in the pipeline.

Bump RISK_CLASSIFICATION_VERSION any time the point values or score->level
mapping below change, so a report's stamped reference_versions (see
MatchReport.reference_versions, app/reference_data/versions.py) keeps
meaning exactly what it meant when that report was generated -- there's no
per-report JSON blob for this module the way most other steps have one,
since classify_risk's output is a bare string (MatchReport.final_risk_level).
"""
from typing import Optional

RISK_CLASSIFICATION_VERSION = "project-spec-v1"

MISMATCH_BUCKET_POINTS: dict[str, int] = {
    "0 mismatches": 0,
    "<3 mismatches": 1,
    "3-6 mismatches": 2,
}

CPRA_BUCKET_POINTS: dict[str, int] = {
    "<30%": 0,
    "30-60%": 1,
}

SCORE_TO_RISK_LEVEL: dict[int, str] = {
    0: "Low Risk",
    1: "Low-Average Risk",
    2: "High-Average Risk",
    3: "High Risk",
}


def classify_risk(mismatch_bucket_name: str, cpra_bucket_name: str) -> Optional[str]:
    mismatch_points = MISMATCH_BUCKET_POINTS.get(mismatch_bucket_name)
    cpra_points = CPRA_BUCKET_POINTS.get(cpra_bucket_name)
    if mismatch_points is None or cpra_points is None:
        return None
    return SCORE_TO_RISK_LEVEL[mismatch_points + cpra_points]

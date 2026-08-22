# app/tests/unit/test_risk_classification.py
from app.reference_data.risk_classification import classify_risk


def test_zero_mismatches_and_low_pra_is_low_risk():
    assert classify_risk("0 mismatches", "<30%") == "Low Risk"


def test_some_mismatches_or_mid_pra_is_low_average():
    assert classify_risk("<3 mismatches", "<30%") == "Low-Average Risk"
    assert classify_risk("0 mismatches", "30-60%") == "Low-Average Risk"


def test_both_elevated_is_high_average():
    assert classify_risk("<3 mismatches", "30-60%") == "High-Average Risk"
    assert classify_risk("3-6 mismatches", "<30%") == "High-Average Risk"


def test_worst_scored_combination_is_high_risk():
    # 3-6 mismatches (2 pts) + 30-60% cPRA (1 pt) = 3 -> High Risk. This is
    # the worst combination with a defined point value on both axes —
    # anything worse on the mismatch axis halts earlier (Step 3), but cPRA
    # >60% no longer halts (see match_pipeline.py's module docstring) and
    # CAN reach this function now; see test_pra_above_60_percent_is_not_
    # scored_and_returns_none below for that case.
    assert classify_risk("3-6 mismatches", "30-60%") == "High Risk"


def test_pra_above_60_percent_is_not_scored_and_returns_none():
    # Regression test: Step 4 (cPRA) used to halt the pipeline above 60%
    # cPRA, so classify_risk never had to handle that bucket. That gate was
    # removed 2026-08-08 as a clinical category error (cPRA is population-
    # level, not pair-specific), which means a real, non-halted check can
    # now reach Step 7 with a ">60%" cPRA bucket. CPRA_BUCKET_POINTS has no
    # entry for it (no doctor-specified point value exists yet), so this
    # must degrade to None rather than raising KeyError.
    assert classify_risk("0 mismatches", ">60%") is None
    assert classify_risk("3-6 mismatches", ">60%") is None

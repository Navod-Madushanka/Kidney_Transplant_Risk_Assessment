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


def test_worst_reachable_combination_is_high_risk():
    # 3-6 mismatches (2 pts) + 30-60% PRA (1 pt) = 3 -> High Risk. This is
    # the worst combination that can ever reach Step 7 — anything worse on
    # either axis halts earlier (Step 3 or Step 4), and PRA >60% never
    # reaches this function at all.
    assert classify_risk("3-6 mismatches", "30-60%") == "High Risk"

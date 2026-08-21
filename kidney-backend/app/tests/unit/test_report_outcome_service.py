# app/tests/unit/test_report_outcome_service.py
import pytest

from app.reference_data.report_outcome import (
    VERDICT_CANNOT_ASSESS,
    VERDICT_COMPATIBLE,
    VERDICT_NOT_COMPATIBLE,
    VERDICT_PROCEED_CAUTION,
)
from app.services.report_outcome_service import build_report_outcome

ABO_RESULT = {"is_compatible": True, "recipient_type": "O", "donor_type": "A"}
MISMATCH_RESULT_COMPLETE = {
    "total_mismatches": 1,
    "bucket_name": "<3 mismatches",
    "is_halted": False,
    "data_completeness": True,
    "missing_inputs": [],
}
MISMATCH_RESULT_INCOMPLETE = {
    "total_mismatches": 4,
    "bucket_name": "3-6 mismatches",
    "is_halted": False,
    "data_completeness": False,
    "missing_inputs": ["donor DRB1 typing"],
}
PRA_BUCKET_LOW = {
    "bucket_name": "<30%",
    "percent": 10.0,
    "is_halted": False,
    "has_sufficient_data": True,
}
PRA_BUCKET_HIGH = {
    "bucket_name": ">60%",
    "percent": 75.0,
    "is_halted": False,
    "has_sufficient_data": True,
}
DSA_CLEAR = {"is_halted": False, "requires_review": False, "matches": []}
DSA_REVIEW = {
    "is_halted": False,
    "requires_review": True,
    "matches": [{"antigen": "B44", "mfi": 2500, "severity": "moderate", "warning_message": "..."}],
}
DSA_UNMAPPED_ANTIBODY = {
    "is_halted": False,
    "requires_review": True,
    "matches": [],
    "unmapped_antibodies": [{"antigen": "B*44:02", "mfi": 12000.0, "reason": "..."}],
}


@pytest.mark.parametrize(
    "overall_status",
    [
        "halted_abo_fail",
        "halted_mismatch_reject",
        "halted_dsa_trigger",
        "halted_crossmatch_positive",
        "pending_crossmatch",
        "completed",
    ],
)
def test_every_overall_status_produces_a_non_null_outcome_with_a_valid_verdict(overall_status):
    outcome = build_report_outcome(
        overall_status=overall_status,
        abo_result=ABO_RESULT,
        mismatch_result=MISMATCH_RESULT_COMPLETE,
        pra_bucket_result=PRA_BUCKET_LOW,
        dsa_result=DSA_CLEAR,
        crossmatch_result={
            "is_positive": overall_status == "halted_crossmatch_positive",
            "is_halted": overall_status == "halted_crossmatch_positive",
        },
        final_risk_level="Low Risk" if overall_status == "completed" else None,
    )
    assert outcome is not None
    assert outcome.verdict in {
        VERDICT_NOT_COMPATIBLE,
        VERDICT_CANNOT_ASSESS,
        VERDICT_PROCEED_CAUTION,
        VERDICT_COMPATIBLE,
    }


def test_row_1_any_halted_status_is_not_compatible():
    for status in (
        "halted_abo_fail",
        "halted_mismatch_reject",
        "halted_dsa_trigger",
        "halted_crossmatch_positive",
    ):
        outcome = build_report_outcome(overall_status=status, abo_result=ABO_RESULT)
        assert outcome.verdict == VERDICT_NOT_COMPATIBLE
        assert outcome.risk_level is None


def test_row_2_pending_crossmatch_is_cannot_assess():
    outcome = build_report_outcome(overall_status="pending_crossmatch", abo_result=ABO_RESULT)
    assert outcome.verdict == VERDICT_CANNOT_ASSESS
    assert outcome.risk_level is None


def test_row_3_completed_with_incomplete_typing_is_cannot_assess():
    outcome = build_report_outcome(
        overall_status="completed",
        abo_result=ABO_RESULT,
        mismatch_result=MISMATCH_RESULT_INCOMPLETE,
        pra_bucket_result=PRA_BUCKET_LOW,
        dsa_result=DSA_CLEAR,
        final_risk_level=None,
    )
    assert outcome.verdict == VERDICT_CANNOT_ASSESS
    assert outcome.risk_level is None
    assert "donor DRB1 typing" in outcome.action_required


def test_row_4_completed_with_high_cpra_is_proceed_with_caution_not_cannot_assess():
    """Regression: a completed check with cPRA >60% has passed every
    pair-specific gate (ABO/mismatch/DSA/crossmatch) for this exact donor.
    The missing final_risk_level is a missing *policy* decision (no agreed
    point value for the >60% band), not missing clinical data — so this
    must be proceed_with_caution, never cannot_assess."""
    outcome = build_report_outcome(
        overall_status="completed",
        abo_result=ABO_RESULT,
        mismatch_result=MISMATCH_RESULT_COMPLETE,
        pra_bucket_result=PRA_BUCKET_HIGH,
        dsa_result=DSA_CLEAR,
        final_risk_level=None,
    )
    assert outcome.verdict == VERDICT_PROCEED_CAUTION
    assert outcome.risk_level is None
    flag_codes = [flag["code"] for flag in outcome.review_flags]
    assert "unclassified_risk" in flag_codes
    assert "high_cpra" in flag_codes


def test_row_5_completed_with_review_flag_is_proceed_with_caution():
    outcome = build_report_outcome(
        overall_status="completed",
        abo_result=ABO_RESULT,
        mismatch_result=MISMATCH_RESULT_COMPLETE,
        pra_bucket_result=PRA_BUCKET_LOW,
        dsa_result=DSA_REVIEW,
        final_risk_level="Low-Average Risk",
    )
    assert outcome.verdict == VERDICT_PROCEED_CAUTION
    assert outcome.risk_level == "Low-Average Risk"
    assert any(flag["code"] == "dsa_requires_review" for flag in outcome.review_flags)


def test_unmapped_antibody_is_a_visible_review_flag_not_dropped():
    # Regression: an antibody the DSA check couldn't map to any donor
    # antigen (e.g. entered allele-level) must never look identical to "no
    # antibody against this donor" -- it has to surface as its own review
    # flag naming the antigen and MFI, distinct from the ordinary
    # weak/moderate DSA-match flag.
    outcome = build_report_outcome(
        overall_status="completed",
        abo_result=ABO_RESULT,
        mismatch_result=MISMATCH_RESULT_COMPLETE,
        pra_bucket_result=PRA_BUCKET_LOW,
        dsa_result=DSA_UNMAPPED_ANTIBODY,
        final_risk_level="Low Risk",
    )
    assert outcome.verdict == VERDICT_PROCEED_CAUTION
    flag_codes = [flag["code"] for flag in outcome.review_flags]
    assert "unmapped_antibody" in flag_codes
    unmapped_flag = next(f for f in outcome.review_flags if f["code"] == "unmapped_antibody")
    assert "B*44:02" in unmapped_flag["detail"]
    assert "12000" in unmapped_flag["detail"]


def test_row_6_completed_with_no_flags_is_compatible():
    outcome = build_report_outcome(
        overall_status="completed",
        abo_result=ABO_RESULT,
        mismatch_result=MISMATCH_RESULT_COMPLETE,
        pra_bucket_result=PRA_BUCKET_LOW,
        dsa_result=DSA_CLEAR,
        final_risk_level="Low Risk",
    )
    assert outcome.verdict == VERDICT_COMPATIBLE
    assert outcome.risk_level == "Low Risk"
    assert outcome.review_flags == []
    assert outcome.action_required is None


@pytest.mark.parametrize(
    "overall_status,expected_step",
    [
        ("halted_abo_fail", 1),
        ("halted_mismatch_reject", 3),
        ("halted_dsa_trigger", 5),
        ("halted_crossmatch_positive", 6),
        ("pending_crossmatch", 6),
    ],
)
def test_determined_at_step_matches_the_halting_step(overall_status, expected_step):
    outcome = build_report_outcome(overall_status=overall_status, abo_result=ABO_RESULT)
    assert outcome.determined_at_step == expected_step


def test_abo_fail_headline_names_actual_blood_types():
    outcome = build_report_outcome(
        overall_status="halted_abo_fail",
        abo_result={"is_compatible": False, "recipient_type": "O", "donor_type": "A"},
    )
    assert "O" in outcome.detail
    assert "A" in outcome.detail

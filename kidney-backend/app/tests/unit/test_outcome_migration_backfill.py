# app/tests/unit/test_outcome_migration_backfill.py
"""
Verifies the frozen `_build_outcome` copy inside the
7a8b6052701d_add_outcome_to_match_reports migration (which backfills
`outcome` on pre-existing match_reports rows) produces the same result as
the live app.services.report_outcome_service.build_report_outcome for a
representative pre-existing report -- i.e. the migration's backfill is
correct, not just that it runs without raising.

Imported by file path via importlib rather than a normal `import` statement
because the migration's module name starts with a digit and lives outside
any package (alembic/versions has no __init__.py).
"""
import importlib.util
from pathlib import Path

from app.services.report_outcome_service import build_report_outcome

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "7a8b6052701d_add_outcome_to_match_reports.py"
)
_spec = importlib.util.spec_from_file_location("outcome_migration_7a8b6052701d", _MIGRATION_PATH)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def test_migration_backfill_matches_the_live_service_for_a_completed_report():
    abo_result = {"is_compatible": True, "recipient_type": "AB", "donor_type": "O"}
    mismatch_result = {
        "total_mismatches": 3,
        "bucket_name": "3-6 mismatches",
        "is_halted": False,
        "data_completeness": True,
        "missing_inputs": [],
    }
    pra_bucket_result = {"bucket_name": "<30%", "percent": 0.0, "is_halted": False, "has_sufficient_data": True}
    dsa_result = {"is_halted": False, "requires_review": False, "matches": []}
    final_risk_level = "High-Average Risk"

    live_outcome = build_report_outcome(
        overall_status="completed",
        abo_result=abo_result,
        mismatch_result=mismatch_result,
        pra_bucket_result=pra_bucket_result,
        dsa_result=dsa_result,
        final_risk_level=final_risk_level,
    )
    migration_outcome = _migration._build_outcome(
        "completed", abo_result, mismatch_result, pra_bucket_result, dsa_result, final_risk_level
    )

    assert migration_outcome["verdict"] == live_outcome.verdict
    assert migration_outcome["risk_level"] == live_outcome.risk_level
    assert migration_outcome["determined_at_step"] == live_outcome.determined_at_step
    assert migration_outcome["review_flags"] == live_outcome.review_flags


def test_migration_backfill_matches_the_live_service_for_a_halted_report():
    abo_result = {"is_compatible": False, "recipient_type": "O", "donor_type": "A"}

    live_outcome = build_report_outcome(overall_status="halted_abo_fail", abo_result=abo_result)
    migration_outcome = _migration._build_outcome(
        "halted_abo_fail", abo_result, None, None, None, None
    )

    assert migration_outcome["verdict"] == live_outcome.verdict == "not_compatible"
    assert migration_outcome["headline"] == live_outcome.headline
    assert migration_outcome["detail"] == live_outcome.detail
    assert migration_outcome["determined_at_step"] == live_outcome.determined_at_step


def test_migration_backfill_matches_row_4_high_cpra_case():
    abo_result = {"is_compatible": True, "recipient_type": "O", "donor_type": "O"}
    mismatch_result = {
        "total_mismatches": 0,
        "bucket_name": "0 mismatches",
        "is_halted": False,
        "data_completeness": True,
        "missing_inputs": [],
    }
    pra_bucket_result = {"bucket_name": ">60%", "percent": 75.0, "is_halted": False, "has_sufficient_data": True}
    dsa_result = {"is_halted": False, "requires_review": False, "matches": []}

    live_outcome = build_report_outcome(
        overall_status="completed",
        abo_result=abo_result,
        mismatch_result=mismatch_result,
        pra_bucket_result=pra_bucket_result,
        dsa_result=dsa_result,
        final_risk_level=None,
    )
    migration_outcome = _migration._build_outcome(
        "completed", abo_result, mismatch_result, pra_bucket_result, dsa_result, None
    )

    assert migration_outcome["verdict"] == live_outcome.verdict == "proceed_with_caution"
    assert migration_outcome["risk_level"] is None
    assert {f["code"] for f in migration_outcome["review_flags"]} == {
        f["code"] for f in live_outcome.review_flags
    }

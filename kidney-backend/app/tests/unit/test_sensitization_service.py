# app/tests/unit/test_sensitization_service.py
from app.services.sensitization_service import calculate_sensitization_score


def test_no_events_gives_zero_score_and_unchanged_cutoff():
    result = calculate_sensitization_score(event_types=[], base_mfi_cutoff=2000.0)

    assert result.total_score == 0.0
    assert result.adjusted_mfi_cutoff == 2000.0


def test_single_event_previous_transplant():
    result = calculate_sensitization_score(
        event_types=["previous_transplant"], base_mfi_cutoff=2000.0
    )

    assert result.total_score == 2.0
    assert result.adjusted_mfi_cutoff == 1800.0


def test_multiple_events_sum_correctly():
    result = calculate_sensitization_score(
        event_types=["previous_transplant", "pregnancy", "blood_transfusion"],
        base_mfi_cutoff=2000.0,
    )

    assert result.total_score == 3.5
    assert result.adjusted_mfi_cutoff == 1650.0
    assert len(result.event_breakdown) == 3


def test_repeated_event_type_counts_each_occurrence():
    result = calculate_sensitization_score(
        event_types=["blood_transfusion", "blood_transfusion"],
        base_mfi_cutoff=2000.0,
    )

    assert result.total_score == 1.0
    assert len(result.event_breakdown) == 2
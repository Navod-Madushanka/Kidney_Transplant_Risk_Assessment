# app/tests/unit/test_cpra_service.py
import pytest

from app.services.cpra_service import calculate_cpra

REFERENCE_SAMPLE_SIZE = 714
REFERENCE_VERSION = "test-v1"
REFERENCE_CITATION = "test citation"


def _calculate(unacceptable_antigens, antigen_frequencies):
    return calculate_cpra(
        unacceptable_antigens=unacceptable_antigens,
        antigen_frequencies=antigen_frequencies,
        reference_sample_size=REFERENCE_SAMPLE_SIZE,
        reference_table_version=REFERENCE_VERSION,
        source_citation=REFERENCE_CITATION,
    )


def test_single_antigen_uses_its_frequency_directly():
    result = _calculate(["A2"], {"A2": 0.2})

    assert result.cpra_percentage == 20.0


def test_multiple_antigens_combine_via_union_rule():
    # Union-of-independent-events rule: 0.2 + 0.1 - 0.2*0.1 = 0.28
    result = _calculate(["A2", "B7"], {"A2": 0.2, "B7": 0.1})

    assert result.cpra_percentage == pytest.approx(28.0)


def test_antigen_missing_from_reference_table_defaults_to_zero_frequency():
    result = _calculate(["A2", "Z99"], {"A2": 0.2})

    assert result.cpra_percentage == 20.0


def test_empty_unacceptable_antigens_yields_zero_percent_and_ok_message():
    result = _calculate([], {"A2": 0.2})

    assert result.cpra_percentage == 0.0
    assert result.message == "OK"


def test_has_sufficient_data_is_always_true():
    result = _calculate([], {})

    assert result.has_sufficient_data is True


def test_message_reports_how_many_antigens_matched_the_table():
    result = _calculate(["A2", "B7", "Z99"], {"A2": 0.2, "B7": 0.1})

    assert result.message == "2 of 3 unacceptable antigens matched the reference frequency table"


def test_reference_table_metadata_passes_through_unchanged():
    result = _calculate(["A2"], {"A2": 0.2})

    assert result.sample_size == REFERENCE_SAMPLE_SIZE
    assert result.reference_table_version == REFERENCE_VERSION
    assert result.source_citation == REFERENCE_CITATION


def test_repeated_antigen_does_not_double_count():
    # Part I (I9): a real Sero group legitimately spans several distinct
    # beads (e.g. "A24" on beads 011/012 at different MFIs -- see
    # ocr-service's bead_reconciliation.py), so a sensitised patient's
    # antigen list can legitimately contain the same name twice. Before
    # deduplication, combining "A24" into the union-probability formula
    # twice computed `2f - f^2` instead of `f`, overstating cPRA for
    # essentially every sensitised patient -- independent of any OCR
    # error. ["A24", "A24", "A2"] must equal ["A24", "A2"].
    with_repeat = _calculate(["A24", "A24", "A2"], {"A24": 0.15, "A2": 0.2})
    without_repeat = _calculate(["A24", "A2"], {"A24": 0.15, "A2": 0.2})

    assert with_repeat.cpra_percentage == without_repeat.cpra_percentage
    assert with_repeat.message == without_repeat.message


def test_repeated_antigen_message_reports_unique_count():
    result = _calculate(["A24", "A24", "A2"], {"A24": 0.15, "A2": 0.2})

    assert result.message == "2 of 2 unacceptable antigens matched the reference frequency table"

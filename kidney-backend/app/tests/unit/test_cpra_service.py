# app/tests/unit/test_cpra_service.py
import pytest

from app.services.cpra_service import calculate_cpra

REFERENCE_SAMPLE_SIZE = 714
REFERENCE_VERSION = "test-v1"
REFERENCE_CITATION = "test citation"


def _calculate(sensitized_antigens, antigen_frequencies):
    return calculate_cpra(
        sensitized_antigens=sensitized_antigens,
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


def test_empty_sensitized_antigens_yields_zero_percent_and_ok_message():
    result = _calculate([], {"A2": 0.2})

    assert result.cpra_percentage == 0.0
    assert result.message == "OK"


def test_has_sufficient_data_is_always_true():
    result = _calculate([], {})

    assert result.has_sufficient_data is True


def test_message_reports_how_many_antigens_matched_the_table():
    result = _calculate(["A2", "B7", "Z99"], {"A2": 0.2, "B7": 0.1})

    assert result.message == "2 of 3 sensitized antigens matched the reference frequency table"


def test_reference_table_metadata_passes_through_unchanged():
    result = _calculate(["A2"], {"A2": 0.2})

    assert result.sample_size == REFERENCE_SAMPLE_SIZE
    assert result.reference_table_version == REFERENCE_VERSION
    assert result.source_citation == REFERENCE_CITATION

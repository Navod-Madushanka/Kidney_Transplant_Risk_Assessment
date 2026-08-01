# app/tests/unit/test_json_parsing.py
#
# Covers app/llm/client.py::_try_parse_json — the layer that decides
# whether a model response counts as valid JSON (and therefore whether
# chat_json needs its one retry). No network involved.
from app.llm.client import _try_parse_json


def test_clean_json():
    assert _try_parse_json('{"a": 1}') == {"a": 1}


def test_json_wrapped_in_markdown_fence():
    text = '```json\n{"a": 1}\n```'
    assert _try_parse_json(text) == {"a": 1}


def test_json_wrapped_in_bare_fence():
    text = '```\n{"a": 1}\n```'
    assert _try_parse_json(text) == {"a": 1}


def test_json_with_stray_prose_around_it():
    # Observed in real runs: the model apologizing or narrating despite
    # JSON_ONLY_INSTRUCTION. The outermost {...} span should still parse.
    text = 'Sure, here is the JSON:\n{"a": 1}\nLet me know if you need more.'
    assert _try_parse_json(text) == {"a": 1}


def test_empty_string_returns_none():
    assert _try_parse_json("") is None


def test_whitespace_only_returns_none():
    assert _try_parse_json("   \n\t  ") is None


def test_not_json_at_all_returns_none():
    assert _try_parse_json("I cannot read this image.") is None


def test_trailing_comma_returns_none():
    assert _try_parse_json('{"a": 1,}') is None


def test_truncated_json_returns_none():
    # The realistic failure case: generation got cut off mid-object
    # (num_predict budget exhausted, or a repetition-loop derailment).
    assert _try_parse_json('{"a": 1, "b": [1, 2,') is None


def test_nested_object_survives():
    text = '{"patient_details": {"full_name": "X"}, "patient_hla": [{"locus": "A"}]}'
    parsed = _try_parse_json(text)
    assert parsed["patient_details"]["full_name"] == "X"
    assert parsed["patient_hla"][0]["locus"] == "A"

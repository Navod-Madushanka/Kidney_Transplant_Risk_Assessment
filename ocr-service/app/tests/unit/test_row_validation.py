# app/tests/unit/test_row_validation.py
#
# Covers the pure post-processing helpers in app/extraction/llm_extract.py
# that sit between "whatever JSON the model returned" and the frozen
# external `structured` contract: _validate_hla_rows (locus allowlist),
# _dedupe_rows / _coerce_mfi (bead specificity tile merge). No network.
#
# NOTE: a _parse_csv_rows helper briefly lived here (Phase 1 speed pass,
# 2026-08-04) for a CSV-envelope bead-specificity response format that was
# tried and reverted after a real live test showed it triggering a worse
# repetition-loop hallucination than the JSON-array format it replaced —
# see BEAD_SPECIFICITY_PROMPT's own "TRIED AND REVERTED" comment in
# app/llm/prompts.py for the full story. Removed along with the function.
from app.extraction.llm_extract import _coerce_mfi, _dedupe_rows, _validate_hla_rows


# --- _validate_hla_rows ---

def test_valid_canonical_loci_pass_through():
    rows = [
        {"locus": "A", "allele_1": "29", "allele_2": "33"},
        {"locus": "DRB3,4,5", "allele_1": "DRB3*02", "allele_2": "DRB4*01"},
    ]
    valid, warning = _validate_hla_rows(rows)
    assert valid == rows
    assert warning is None


def test_unrecognized_locus_dropped_and_warned():
    # Real observed failure mode (Phase 1): the model occasionally spells a
    # locus differently than the canonical set, or hallucinates one that
    # isn't a real column. Must be dropped, not trusted verbatim -- this is
    # clinical lab data feeding a validator downstream.
    rows = [
        {"locus": "A", "allele_1": "29", "allele_2": "33"},
        {"locus": "DRB1I", "allele_1": "03", "allele_2": "04"},  # I/1 confusion
    ]
    valid, warning = _validate_hla_rows(rows)
    assert len(valid) == 1
    assert valid[0]["locus"] == "A"
    assert warning == "model_returned_unrecognized_locus:DRB1I"


def test_missing_locus_key_reported_as_missing_placeholder():
    rows = [{"allele_1": "29", "allele_2": "33"}]  # no "locus" key at all
    valid, warning = _validate_hla_rows(rows)
    assert valid == []
    assert warning == "model_returned_unrecognized_locus:<missing>"


def test_non_list_input_returns_empty_no_crash():
    # Defensive: a malformed model response could put anything under
    # patient_hla/donor_hla. Must not raise.
    valid, warning = _validate_hla_rows("not a list")
    assert valid == []
    assert warning is None


def test_alleles_coerced_to_strings():
    # The model sometimes returns numeric-looking alleles unquoted.
    rows = [{"locus": "A", "allele_1": 29, "allele_2": 33}]
    valid, _ = _validate_hla_rows(rows)
    assert valid[0]["allele_1"] == "29"
    assert valid[0]["allele_2"] == "33"


# --- _coerce_mfi ---

def test_coerce_mfi_plain_number():
    assert _coerce_mfi(23706.91) == 23706.91


def test_coerce_mfi_string_with_comma():
    assert _coerce_mfi("23,706.91") == 23706.91


def test_coerce_mfi_none_stays_none():
    assert _coerce_mfi(None) is None


def test_coerce_mfi_unparseable_string_returns_none():
    assert _coerce_mfi("illegible") is None


def test_coerce_mfi_int():
    assert _coerce_mfi(490) == 490.0


# --- _dedupe_rows ---

def test_dedupe_exact_duplicate_from_tile_overlap():
    # Row-band tiles overlap 12% (app/extraction/tiling.py) specifically so
    # a row near a tile boundary can get read by two adjacent tiles -- this
    # is the intended, expected duplicate case.
    rows = [
        {"antigen": "A23", "mfi": 490.5},
        {"antigen": "A23", "mfi": 490.5},
    ]
    merged = _dedupe_rows(rows)
    assert merged == [{"antigen": "A23", "mfi": 490.5}]


def test_dedupe_is_case_and_whitespace_insensitive_on_antigen():
    rows = [
        {"antigen": "A23", "mfi": 490.5},
        {"antigen": " a23 ", "mfi": 490.5},
    ]
    merged = _dedupe_rows(rows)
    assert len(merged) == 1


def test_dedupe_keeps_same_antigen_different_mfi():
    # Real, legitimate case: the same antigen name can appear on multiple
    # distinct rows of the chart with genuinely different MFI values (see
    # the bead_specificity_anchor.json fixture -- "A24" appears twice with
    # different values). Must not be collapsed.
    rows = [
        {"antigen": "A24", "mfi": 23582.09},
        {"antigen": "A24", "mfi": 23590.10},
    ]
    merged = _dedupe_rows(rows)
    assert len(merged) == 2


def test_dedupe_drops_rows_with_empty_antigen():
    rows = [{"antigen": "", "mfi": 100.0}, {"antigen": "A23", "mfi": 490.5}]
    merged = _dedupe_rows(rows)
    assert merged == [{"antigen": "A23", "mfi": 490.5}]


def test_dedupe_skips_non_dict_entries_without_crashing():
    rows = ["not a row", {"antigen": "A23", "mfi": 490.5}]
    merged = _dedupe_rows(rows)
    assert merged == [{"antigen": "A23", "mfi": 490.5}]


def test_dedupe_coerces_mfi_formatting_before_keying():
    # "23,706.91" and 23706.91 must hash to the same dedupe key even though
    # one arrived as a formatted string.
    rows = [
        {"antigen": "A23", "mfi": "23,706.91"},
        {"antigen": "A23", "mfi": 23706.91},
    ]
    merged = _dedupe_rows(rows)
    assert len(merged) == 1
    assert merged[0]["mfi"] == 23706.91

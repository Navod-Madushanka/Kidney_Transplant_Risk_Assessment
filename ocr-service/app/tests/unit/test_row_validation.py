# app/tests/unit/test_row_validation.py
#
# Covers _validate_hla_rows (locus allowlist) in
# app/extraction/llm_extract.py -- the pure post-processing helper that
# sits between "whatever JSON the model returned" and the frozen external
# `structured` contract for HLA typing. No network.
#
# NOTE: the bead-specificity coercion/reconciliation tests that used to
# live here (_coerce_mfi, _dedupe_rows) moved to
# app/tests/unit/test_bead_reconciliation.py when _dedupe_rows was
# replaced by reconcile_bead_rows (Part I -- see
# app/extraction/bead_reconciliation.py's module docstring for why the old
# exact-match dedupe was wrong).
#
# A _parse_csv_rows helper also briefly lived here (Phase 1 speed pass,
# 2026-08-04) for a CSV-envelope bead-specificity response format that was
# tried and reverted -- see BEAD_SPECIFICITY_PROMPT's own "TRIED AND
# REVERTED" comment in app/llm/prompts.py for the full story.
from app.extraction.llm_extract import _validate_hla_rows


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

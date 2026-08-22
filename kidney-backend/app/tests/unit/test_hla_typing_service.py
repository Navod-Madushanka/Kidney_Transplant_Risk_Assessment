# app/tests/unit/test_hla_typing_service.py
from app.services.hla_typing_service import (
    hla_antigen_designation,
    locus_for_antigen_designation,
    normalize_antibody_antigen,
)


def test_same_scheme_loci_pass_through_unchanged():
    # A/B's molecular locus name already matches their serological name, so
    # these have always worked. (HLA-C looks the same at a glance but isn't
    # -- see test_c_locus_maps_to_cw_serological_prefix below.)
    assert hla_antigen_designation("A", "29") == "A29"
    assert hla_antigen_designation("B", "07") == "B7"


def test_drb1_dqb1_dpb1_map_to_serological_prefix():
    # Real bug fixed 2026-08-02: a real anti-DR13 antibody was invisible to
    # the DSA check because this used to return "DRB113" here, which never
    # matches a real antibody screen's "DR13".
    assert hla_antigen_designation("DRB1", "13") == "DR13"
    assert hla_antigen_designation("DQB1", "05") == "DQ5"
    assert hla_antigen_designation("DPB1", "04") == "DP4"


def test_c_locus_maps_to_cw_serological_prefix():
    # Real bug found 2026-08-03 running the full pipeline against a real
    # shared bead-specificity chart: unlike A/B, HLA-C's serological name
    # isn't the bare locus letter -- real antibody screens name these
    # antigens "Cw3", "Cw15", etc., never "C3"/"C15". This used to return
    # "C3" here, same class of bug as the DRB1/DQB1/DPB1 one above.
    assert hla_antigen_designation("C", "03") == "Cw3"


def test_leading_zeros_stripped_after_prefix_mapping():
    assert hla_antigen_designation("DRB1", "04") == "DR4"


def test_all_zero_allele_does_not_strip_to_empty():
    assert hla_antigen_designation("B", "00") == "B0"


def test_normalize_antibody_antigen_strips_bw_suffix():
    # Real bug found 2026-08-03: real charts often record a B-locus antigen
    # combined with its broad Bw4/Bw6 cross-reactive group in one string,
    # which never exact-matched hla_antigen_designation()'s bare output.
    assert normalize_antibody_antigen("B45,Bw6") == "B45"
    assert normalize_antibody_antigen("B7,Bw4") == "B7"


def test_normalize_antibody_antigen_handles_period_separator():
    # OCR sometimes reads the comma as a period on this same suffix.
    assert normalize_antibody_antigen("B41.Bw6") == "B41"


def test_normalize_antibody_antigen_is_case_insensitive_on_bw():
    assert normalize_antibody_antigen("B45,bw6") == "B45"


def test_normalize_antibody_antigen_passes_through_plain_antigen():
    assert normalize_antibody_antigen("DR13") == "DR13"
    assert normalize_antibody_antigen("A29") == "A29"


def test_normalize_antibody_antigen_does_not_touch_unrelated_suffix():
    # Guard against accidentally masking a separate, already-known bug: a
    # real chart had 26 real rows all mislabeled with the identical antigen
    # string "B40.01" by the OCR extraction (see ocr-service/app/llm/
    # prompts.py comments) -- that's a distinct, open extraction-accuracy
    # problem, not a Bw-suffix, and this function must not paper over it by
    # stripping ".01" as if it matched the Bw pattern.
    assert normalize_antibody_antigen("B40.01") == "B40.01"


def test_normalize_antibody_antigen_does_not_touch_allele_level_designation():
    # Allele-level designations ("B*07:02") are a different, unmapped
    # naming scheme entirely -- out of scope here, see the module docstring.
    assert normalize_antibody_antigen("B*07:02") == "B*07:02"


def test_locus_for_antigen_designation_same_scheme_loci():
    assert locus_for_antigen_designation("A29") == "A"
    assert locus_for_antigen_designation("B7") == "B"


def test_locus_for_antigen_designation_serological_prefixes():
    assert locus_for_antigen_designation("DR13") == "DRB1"
    assert locus_for_antigen_designation("DQ5") == "DQB1"
    assert locus_for_antigen_designation("DP4") == "DPB1"
    assert locus_for_antigen_designation("Cw3") == "C"


def test_locus_for_antigen_designation_unrecognized_returns_none():
    # HLA-E is outside this system's serological-prefix scheme entirely (not
    # DR/DQ/DP/Cw, and doesn't start with "A" or "B" either).
    assert locus_for_antigen_designation("E1") is None


def test_locus_for_antigen_designation_does_not_filter_allele_level_strings():
    # Prefix-only matching resolves a locus letter even for an allele-level
    # string -- callers needing to treat that differently (e.g.
    # dsa_service.check_dsa's _ALLELE_LEVEL_CHARS check) must check for it
    # themselves before falling back to this function.
    assert locus_for_antigen_designation("B*07:02") == "B"

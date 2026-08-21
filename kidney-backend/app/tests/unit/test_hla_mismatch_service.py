# app/tests/unit/test_hla_mismatch_service.py
from app.services.hla_mismatch_service import calculate_mismatch_result


def _typing(a=("", ""), b=("", ""), drb1=("", "")):
    return {"A": list(a), "B": list(b), "DRB1": list(drb1)}


def test_zero_mismatches_when_donor_alleles_all_present_in_patient():
    patient = _typing(a=("29", "33"), b=("07", "58"), drb1=("03", "04"))
    donor = _typing(a=("33", "33"), b=("07", "07"), drb1=("04", "04"))

    result = calculate_mismatch_result(patient, donor)

    assert result.total_mismatches == 0
    assert result.bucket_name == "0 mismatches"
    assert result.is_halted is False


def test_other_loci_are_ignored_even_with_totally_different_alleles():
    # C and DQB1 mismatches (not in MISMATCH_COUNTED_LOCI) must not count.
    patient = {"A": ["29", "33"], "B": ["07", "58"], "DRB1": ["03", "04"], "C": ["01", "02"]}
    donor = {"A": ["29", "33"], "B": ["07", "58"], "DRB1": ["03", "04"], "C": ["99", "98"]}

    result = calculate_mismatch_result(patient, donor)

    assert result.total_mismatches == 0


def test_bucket_boundaries():
    # 1-2 -> "<3 mismatches"
    patient = _typing(a=("29", "33"))
    donor = _typing(a=("40", "41"))  # 2 donor alleles, neither in patient -> 2 mismatches
    result = calculate_mismatch_result(patient, donor)
    assert result.total_mismatches == 2
    assert result.bucket_name == "<3 mismatches"
    assert result.is_halted is False


def test_maximum_reachable_mismatches_halts_the_gate():
    # Regression test: each locus stores exactly 2 alleles, so the ceiling
    # across A/B/DRB1 is 2 unique mismatches per locus x 3 loci = 6 total --
    # also exactly MAX_ACCEPTABLE_MISMATCHES. is_halted used to compare with
    # a strict `>`, which made this genuine worst case land in the top
    # bucket ("3-6 mismatches") and still proceed, i.e. the reject path was
    # mathematically unreachable through any real two-allele typing data.
    # `>=` fixes that: a full 6/6 mismatch now actually halts Step 3.
    patient = _typing(a=("01", "02"), b=("01", "02"), drb1=("01", "02"))
    donor = _typing(a=("11", "12"), b=("11", "12"), drb1=("11", "12"))

    result = calculate_mismatch_result(patient, donor)

    assert result.total_mismatches == 6
    assert result.bucket_name == "3-6 mismatches"
    assert result.is_halted is True


def test_five_mismatches_is_the_highest_reachable_pass():
    # One allele short of the 6/6 reject case above (donor's first A allele
    # happens to match the patient) -- confirms the gate's boundary sits
    # exactly at 6, not off by one in either direction.
    patient = _typing(a=("01", "02"), b=("01", "02"), drb1=("01", "02"))
    donor = _typing(a=("01", "12"), b=("11", "12"), drb1=("11", "12"))

    result = calculate_mismatch_result(patient, donor)

    assert result.total_mismatches == 5
    assert result.bucket_name == "3-6 mismatches"
    assert result.is_halted is False


def test_missing_locus_data_counts_as_conservative_worst_case():
    # Patient has no typing at all for A/B/DRB1; donor has alleles for B.
    patient = _typing()  # all empty
    donor = _typing(b=("07", "40"))

    result = calculate_mismatch_result(patient, donor)

    # Missing patient data -> both donor B alleles count as mismatches,
    # rather than silently treating unknown as compatible.
    assert result.total_mismatches == 2
    assert result.bucket_name == "<3 mismatches"


def test_fully_typed_result_is_marked_complete():
    patient = _typing(a=("29", "33"), b=("07", "58"), drb1=("03", "04"))
    donor = _typing(a=("11", "12"), b=("17", "18"), drb1=("13", "14"))

    result = calculate_mismatch_result(patient, donor)

    assert result.data_completeness is True
    assert result.missing_inputs == []


def test_donor_with_no_hla_typing_at_all_is_not_a_perfect_match():
    # Regression test: build_partial_typing_dict fills a wholly-untyped
    # donor's loci with [] (not the placeholder ("", "") strings the other
    # tests in this file use). A set difference against an empty donor set
    # is always empty, so this used to silently score as 0 mismatches --
    # the strongest possible result -- for a donor nobody has typed. Every
    # locus must instead land at the worst case (2), and the result must be
    # flagged incomplete so callers never present this as "Low Risk".
    patient = {"A": ["29", "33"], "B": ["07", "58"], "DRB1": ["03", "04"]}
    donor = {"A": [], "B": [], "DRB1": []}

    result = calculate_mismatch_result(patient, donor)

    assert result.total_mismatches == 6
    assert result.bucket_name == "3-6 mismatches"
    assert result.data_completeness is False
    assert result.missing_inputs == ["donor A typing", "donor B typing", "donor DRB1 typing"]
    # Regression: 3 untyped loci impute to exactly MAX_ACCEPTABLE_MISMATCHES
    # (6), which used to trip is_halted even though nothing was actually
    # measured -- reported as a confirmed "Not Compatible" reject instead of
    # an unmeasured "cannot assess". is_halted must never fire on imputed
    # data; only Step 7's completed-but-incomplete path may report this.
    assert result.is_halted is False


def test_patient_with_no_hla_typing_at_all_is_also_incomplete():
    # Same worst-case count as the donor-missing case above, but this also
    # confirms the two sides are treated symmetrically -- the pre-fix code
    # already gave 6 here, but only because the empty side was the *patient*
    # (the set doing the subtracting), not because it was handled correctly.
    patient = {"A": [], "B": [], "DRB1": []}
    donor = {"A": ["29", "33"], "B": ["07", "58"], "DRB1": ["03", "04"]}

    result = calculate_mismatch_result(patient, donor)

    assert result.total_mismatches == 6
    assert result.bucket_name == "3-6 mismatches"
    assert result.data_completeness is False
    assert result.missing_inputs == [
        "patient A typing",
        "patient B typing",
        "patient DRB1 typing",
    ]
    assert result.is_halted is False


def test_donor_missing_a_single_locus_does_not_silently_improve_the_score():
    # Regression test: a donor missing only DRB1 typing, fully mismatched at
    # A and B (2 + 2 = 4), used to land on 4 total (the DRB1 locus's empty
    # set contributing 0) instead of correctly scoring DRB1 at its worst
    # case too (4 + 2 = 6) -- i.e. incomplete data was silently *improving*
    # the mismatch count relative to a fully-typed, fully-mismatched donor.
    patient = _typing(a=("01", "02"), b=("01", "02"), drb1=("01", "02"))
    donor = {"A": ["11", "12"], "B": ["11", "12"], "DRB1": []}

    result = calculate_mismatch_result(patient, donor)

    assert result.total_mismatches == 6
    assert result.bucket_name == "3-6 mismatches"
    assert result.data_completeness is False
    assert result.missing_inputs == ["donor DRB1 typing"]
    assert result.is_halted is False

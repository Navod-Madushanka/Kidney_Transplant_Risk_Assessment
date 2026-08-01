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


def test_maximum_reachable_mismatches_lands_in_top_bucket_without_halting():
    # Each locus stores exactly 2 alleles, so the ceiling across A/B/DRB1 is
    # 2 unique mismatches per locus x 3 loci = 6 total. That means the ">6
    # mismatches" reject bucket can never actually be reached through normal
    # two-allele typing data — MAX_ACCEPTABLE_MISMATCHES (6) is the true
    # ceiling in practice, and this confirms it lands in the top defined
    # bucket ("3-6 mismatches") and still proceeds rather than halting.
    patient = _typing(a=("01", "02"), b=("01", "02"), drb1=("01", "02"))
    donor = _typing(a=("11", "12"), b=("11", "12"), drb1=("11", "12"))

    result = calculate_mismatch_result(patient, donor)

    assert result.total_mismatches == 6
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

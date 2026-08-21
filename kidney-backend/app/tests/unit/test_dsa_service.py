# app/tests/unit/test_dsa_service.py
from app.reference_data.dsa_threshold import DSA_MFI_FLOOR
from app.services.dsa_service import PatientAntibody, check_dsa


def test_no_dsa_found_returns_clear():
    patient_antibodies = [PatientAntibody(antigen="A2", mfi=3000)]
    donor_hla_antigens = ["B7", "DR15"]  # no overlap with patient's high-MFI antigen

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is False
    assert result.requires_review is False
    assert result.matches == []


def test_strong_dsa_halts_with_correct_message():
    patient_antibodies = [PatientAntibody(antigen="B7", mfi=6000)]
    donor_hla_antigens = ["B7"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is True
    assert result.requires_review is False
    assert len(result.matches) == 1
    assert result.matches[0].severity == "strong"
    assert "B7" in result.matches[0].warning_message
    assert "6000" in result.matches[0].warning_message


def test_weak_dsa_does_not_halt_but_requires_review():
    patient_antibodies = [PatientAntibody(antigen="B7", mfi=1500)]
    donor_hla_antigens = ["B7"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is False
    assert result.requires_review is True
    assert len(result.matches) == 1
    assert result.matches[0].severity == "weak"


def test_moderate_dsa_does_not_halt_but_requires_review():
    patient_antibodies = [PatientAntibody(antigen="B7", mfi=3500)]
    donor_hla_antigens = ["B7"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is False
    assert result.requires_review is True
    assert len(result.matches) == 1
    assert result.matches[0].severity == "moderate"


def test_multiple_dsa_matches_are_all_reported():
    patient_antibodies = [
        PatientAntibody(antigen="B7", mfi=6000),
        PatientAntibody(antigen="DR15", mfi=2500),
    ]
    donor_hla_antigens = ["B7", "DR15"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is True
    assert result.requires_review is True
    assert len(result.matches) == 2


def test_mfi_below_floor_does_not_trigger():
    patient_antibodies = [PatientAntibody(antigen="B7", mfi=DSA_MFI_FLOOR - 1)]
    donor_hla_antigens = ["B7"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is False
    assert result.requires_review is False
    assert result.matches == []


def test_mfi_exactly_at_floor_is_weak_and_flagged():
    patient_antibodies = [PatientAntibody(antigen="B7", mfi=DSA_MFI_FLOOR)]
    donor_hla_antigens = ["B7"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is False
    assert result.requires_review is True
    assert result.matches[0].severity == "weak"


def test_result_records_the_floor_and_bands_in_force():
    result = check_dsa([], [])

    assert result.floor == DSA_MFI_FLOOR
    assert [band["name"] for band in result.bands] == ["weak", "moderate", "strong"]
    assert result.bands[-1]["max_mfi"] is None


def test_allele_level_antigen_is_flagged_as_unmapped_not_silently_dropped():
    # Regression: an antibody entered allele-level ("B*44:02") can never
    # exact-match a donor's serological designation ("B44") no matter how
    # strong the MFI -- see hla_antigen_designation()'s docstring. Before
    # this fix, a strong DSA entered this way produced no match, no halt,
    # and no flag at all, identical to "the patient has no antibody against
    # this donor". It must now surface as a review flag instead.
    patient_antibodies = [PatientAntibody(antigen="B*44:02", mfi=12000)]
    donor_hla_antigens = ["B44"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is False
    assert result.matches == []
    assert result.requires_review is True
    assert len(result.unmapped_antibodies) == 1
    assert result.unmapped_antibodies[0].antigen == "B*44:02"
    assert result.unmapped_antibodies[0].mfi == 12000


def test_unmatched_antibody_in_valid_format_is_not_flagged_as_unmapped():
    # A patient antibody that simply isn't against any of this donor's
    # antigens is the normal, expected case (most of a sensitized patient's
    # antibody profile has nothing to do with any one specific donor) -- it
    # must not be treated the same as the format problem above.
    patient_antibodies = [PatientAntibody(antigen="A2", mfi=6000)]
    donor_hla_antigens = ["B44"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.unmapped_antibodies == []
    assert result.requires_review is False


def test_allele_level_antigen_below_floor_is_not_flagged():
    patient_antibodies = [PatientAntibody(antigen="B*44:02", mfi=DSA_MFI_FLOOR - 1)]
    donor_hla_antigens = ["B44"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.unmapped_antibodies == []
    assert result.requires_review is False

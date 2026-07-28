# app/tests/unit/test_dsa_service.py
from app.services.dsa_service import DEFAULT_MFI_CUTOFF, PatientAntibody, check_dsa


def test_no_dsa_found_returns_clear():
    patient_antibodies = [PatientAntibody(antigen="A2", mfi=3000)]
    donor_hla_antigens = ["B7", "DR15"]  # no overlap with patient's high-MFI antigen

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is False
    assert result.matches == []


def test_dsa_found_halts_with_correct_message():
    patient_antibodies = [PatientAntibody(antigen="B7", mfi=3500)]
    donor_hla_antigens = ["B7"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is True
    assert len(result.matches) == 1
    assert result.matches[0].antigen == "B7"
    assert "B7" in result.matches[0].warning_message
    assert "3500" in result.matches[0].warning_message


def test_multiple_dsa_matches_are_all_reported():
    patient_antibodies = [
        PatientAntibody(antigen="B7", mfi=3500),
        PatientAntibody(antigen="DR15", mfi=2500),
    ]
    donor_hla_antigens = ["B7", "DR15"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is True
    assert len(result.matches) == 2


def test_mfi_exactly_at_cutoff_does_not_trigger():
    patient_antibodies = [PatientAntibody(antigen="B7", mfi=DEFAULT_MFI_CUTOFF)]
    donor_hla_antigens = ["B7"]

    result = check_dsa(patient_antibodies, donor_hla_antigens)

    assert result.is_halted is False

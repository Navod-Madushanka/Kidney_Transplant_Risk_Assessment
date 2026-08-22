# app/tests/unit/test_reference_versions.py
from app.reference_data.versions import CLINICAL_REFERENCE_VERSIONS

EXPECTED_MODULES = {
    "abo_compatibility",
    "dsa_threshold",
    "hla_antigen_frequencies",
    "hla_weights",
    "mismatch_buckets",
    "pra_buckets",
    "risk_classification",
    "risk_tiers",
    "sensitization_weights",
}


def test_every_expected_reference_data_module_has_a_version():
    assert set(CLINICAL_REFERENCE_VERSIONS.keys()) == EXPECTED_MODULES


def test_every_version_is_a_non_empty_string():
    for module_name, version in CLINICAL_REFERENCE_VERSIONS.items():
        assert isinstance(version, str), f"{module_name} version must be a string"
        assert version, f"{module_name} version must not be empty"

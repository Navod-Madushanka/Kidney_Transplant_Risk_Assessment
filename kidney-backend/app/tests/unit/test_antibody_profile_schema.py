# app/tests/unit/test_antibody_profile_schema.py
import pytest
from pydantic import ValidationError

from app.schemas.antibody_profile import AntibodyProfileEntry


def test_serological_antigen_is_accepted():
    entry = AntibodyProfileEntry(antigen="B44", mfi=12000)
    assert entry.antigen == "B44"


@pytest.mark.parametrize("antigen", ["B*44:02", "DRB1*04:01", "A*02:01"])
def test_allele_level_antigen_is_rejected(antigen):
    # Regression: this format can never match a donor's bare serological
    # designation (hla_antigen_designation() in hla_typing_service.py), so a
    # doctor entering it -- previously encouraged by BeadSpecificityStep.jsx's
    # own placeholder example -- silently lost DSA coverage with no error.
    # Reject it at the boundary instead.
    with pytest.raises(ValidationError, match="serological designation"):
        AntibodyProfileEntry(antigen=antigen, mfi=12000)

# app/schemas/antibody_profile.py
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import AntibodyPanel


class AntibodyProfileEntry(BaseModel):
    antigen: str
    mfi: Decimal
    # Part I (bead-row identity / tile reconciliation) -- all optional and
    # default None: a hand-entered row (BeadSpecificityStep.jsx's manual
    # editor) has no source Bead code, page, or OCR conflict to report.
    # See app/models/antibody_profile.py's own field comments for what
    # each one means and why it's nullable.
    bead_id: str | None = None
    panel: AntibodyPanel | None = None
    extraction_conflict: list[float | None] | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("antigen")
    @classmethod
    def _reject_allele_level_antigen(cls, value: str) -> str:
        # The DSA check (app/services/dsa_service.py) matches antigen strings
        # by exact equality against donor typing built by
        # hla_antigen_designation(), which only ever produces bare
        # serological designations ("B44"). An allele-level designation
        # ("B*44:02", HLA's molecular typing nomenclature -- a different,
        # unmapped naming scheme entirely, see normalize_antibody_antigen's
        # docstring in hla_typing_service.py) can never match that and would
        # silently disappear from DSA matching with no error and no review
        # flag -- a real critical-MFI antibody entered this way looked
        # identical to "no antibody at all". Reject it at the boundary
        # instead of letting it become invisible bad data.
        if "*" in value or ":" in value:
            raise ValueError(
                "Antigen must be a serological designation (e.g. 'B44'), not "
                "an allele-level typing (e.g. 'B*44:02') -- the DSA check "
                "only matches against serological antigen names."
            )
        return value

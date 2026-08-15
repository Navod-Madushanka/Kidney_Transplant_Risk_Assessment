# app/schemas/antibody_profile.py
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

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

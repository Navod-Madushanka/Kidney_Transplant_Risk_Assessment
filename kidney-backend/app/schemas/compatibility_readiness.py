# app/schemas/compatibility_readiness.py
from pydantic import BaseModel


class ReadinessGapResponse(BaseModel):
    code: str
    label: str
    subject: str  # "patient" | "donor"


class CompatibilityReadinessResponse(BaseModel):
    """Mirrors app/services/compatibility_precondition_service.
    CompatibilityReadiness field-for-field -- see that module's docstring
    for what each list means and why missing LKDPI/donor-risk inputs are
    deliberately NOT part of `blocking`."""

    can_run: bool
    blocking: list[ReadinessGapResponse]
    lkdpi_gaps: list[ReadinessGapResponse]
    donor_risk_projection_gaps: list[ReadinessGapResponse]
    donor_risk_contraindication_gaps: list[ReadinessGapResponse]

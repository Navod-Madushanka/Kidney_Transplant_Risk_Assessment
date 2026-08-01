# app/schemas/match_report.py
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CrossmatchInput(BaseModel):
    """Step 6 of the sequential pipeline. Crossmatch is a same-day lab
    result tied to this specific pairing, not stored against the patient or
    donor ahead of time — so it travels with the check request itself
    rather than being looked up server-side like HLA typing or antibody
    profiles. is_positive is the field that actually gates the pipeline;
    the rest are kept for display/reference on the report.
    """

    is_positive: bool
    t_cell_result: Optional[str] = None
    b_cell_result: Optional[str] = None
    remarks: Optional[str] = None


class CompatibilityCheckRequest(BaseModel):
    patient_id: uuid.UUID
    donor_id: uuid.UUID
    # Optional so existing callers that halt before Step 6 (ABO/mismatch/
    # PRA/DSA fail) aren't forced to supply it. If the pipeline reaches
    # Step 6 without one, the report's overall_status comes back as
    # "pending_crossmatch" rather than silently completing without it.
    crossmatch: Optional[CrossmatchInput] = None


class MatchReportResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    donor_id: uuid.UUID
    overall_status: str
    abo_result: dict
    sensitization_result: Optional[dict] = None
    mismatch_result: Optional[dict] = None
    pra_bucket_result: Optional[dict] = None
    dsa_result: Optional[dict] = None
    crossmatch_result: Optional[dict] = None
    hla_scoring_result: Optional[dict] = None
    cpra_result: Optional[dict] = None
    final_risk_level: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

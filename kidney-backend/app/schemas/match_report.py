# app/schemas/match_report.py
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CompatibilityCheckRequest(BaseModel):
    patient_id: uuid.UUID
    donor_id: uuid.UUID


class MatchReportResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    donor_id: uuid.UUID
    overall_status: str
    abo_result: dict
    sensitization_result: Optional[dict] = None
    dsa_result: Optional[dict] = None
    hla_scoring_result: Optional[dict] = None
    cpra_result: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

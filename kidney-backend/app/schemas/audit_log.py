# app/schemas/audit_log.py
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    action: str
    patient_id: Optional[uuid.UUID] = None
    donor_id: Optional[uuid.UUID] = None
    details: Optional[dict] = None
    created_at: datetime
    prev_hash: str
    hash: str

    model_config = ConfigDict(from_attributes=True)


class AuditChainVerificationResponse(BaseModel):
    is_valid: bool
    checked_count: int
    total_count: int
    first_broken_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

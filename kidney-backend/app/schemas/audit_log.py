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

    model_config = ConfigDict(from_attributes=True)
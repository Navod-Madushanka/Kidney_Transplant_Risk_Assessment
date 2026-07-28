# app/schemas/sensitization_event.py
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import SensitizationEventTypeEnum


class SensitizationEventEntry(BaseModel):
    event_type: SensitizationEventTypeEnum
    event_date: date


class SensitizationEventResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    event_type: SensitizationEventTypeEnum
    event_date: date
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

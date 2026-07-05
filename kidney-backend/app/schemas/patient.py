# app/schemas/patient.py
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BloodType


class PatientCreate(BaseModel):
    full_name: str
    date_of_birth: date
    blood_type: BloodType


class PatientResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
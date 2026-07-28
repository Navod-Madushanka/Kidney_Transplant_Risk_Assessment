# app/schemas/patient.py
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BloodType, RhFactor


class PatientCreate(BaseModel):
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    rh_factor: RhFactor          # add this line
    nic_number: str | None = None


class PatientResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    rh_factor: RhFactor          # add this line
    nic_number: str | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

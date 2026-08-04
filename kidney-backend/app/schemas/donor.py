# app/schemas/donor.py
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BloodType, DonorStatus, RhFactor


class DonorCreate(BaseModel):
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    rh_factor: RhFactor
    nic_number: str | None = None


class DonorUpdate(BaseModel):
    """Core demographic fields only — blood_type/rh_factor are permanent
    once set (the compatibility engine and existing reports trust them),
    so they're deliberately absent here rather than editable."""

    full_name: str
    date_of_birth: date
    nic_number: str | None = None


class DonorResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    rh_factor: RhFactor
    nic_number: str | None
    status: DonorStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DonorStatusUpdate(BaseModel):
    status: DonorStatus

# app/schemas/patient.py
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import BloodType, RhFactor, Sex
from app.schemas._validators import normalize_nic

# LKDPI input -- see app/reference_data/lkdpi_model.py. Bound is a typo
# guard, not a clinical ceiling, matching donor.py's _WEIGHT_FIELD-style
# fields.
_WEIGHT_KG_FIELD = Field(default=None, gt=0, le=400, description="kg")


class PatientCreate(BaseModel):
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    rh_factor: RhFactor
    nic_number: str | None = None
    sex: Sex | None = None
    weight_kg: float | None = _WEIGHT_KG_FIELD
    # None means "no claim being made" -> trusted, same contract as
    # hla_typing_verified/antibody_profile_verified's ocr_verified param.
    # Only the compatibility-check wizard ever passes an explicit value.
    details_verified: bool | None = None

    _normalize_nic = field_validator("nic_number")(normalize_nic)


class PatientUpdate(BaseModel):
    """Core demographic fields only — blood_type/rh_factor are permanent
    once set (the compatibility engine and existing reports trust them),
    so they're deliberately absent here rather than editable. sex/weight_kg
    are LKDPI inputs, expected to change over time like the donor clinical
    fields, so they're editable here."""

    full_name: str
    date_of_birth: date
    nic_number: str | None = None
    sex: Sex | None = None
    weight_kg: float | None = _WEIGHT_KG_FIELD
    # None = "no claim being made about this write" -> preserve the
    # record's current details_verified rather than resetting it to
    # trusted -- same _resolve_verified contract as ocr_verified on
    # PUT .../hla-typings (see hla_typing_service.py). Only the
    # compatibility-check wizard, writing to a linked record whose details
    # this write may have just overwritten from a fresh OCR read, ever
    # passes an explicit True/False.
    details_verified: bool | None = None

    _normalize_nic = field_validator("nic_number")(normalize_nic)


class PatientResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    rh_factor: RhFactor
    nic_number: str | None
    sex: Sex | None
    weight_kg: float | None
    hla_typing_verified: bool
    antibody_profile_verified: bool
    details_verified: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

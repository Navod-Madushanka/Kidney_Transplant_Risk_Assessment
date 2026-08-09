# app/schemas/donor.py
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BloodType, DonorStatus, RhFactor

# Bounds are sanity checks against typos/garbage input, not clinical
# accept/reject thresholds -- see Donor model's docstring comment on these
# fields for why nothing in the compatibility pipeline reads them.
_EGFR_FIELD = Field(default=None, gt=0, le=200, description="mL/min/1.73m^2")
_SYSTOLIC_BP_FIELD = Field(default=None, ge=50, le=300, description="mmHg")
_DIASTOLIC_BP_FIELD = Field(default=None, ge=30, le=200, description="mmHg")
_BMI_FIELD = Field(default=None, gt=0, le=100, description="kg/m^2")


class DonorCreate(BaseModel):
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    rh_factor: RhFactor
    nic_number: str | None = None
    egfr: float | None = _EGFR_FIELD
    systolic_bp: int | None = _SYSTOLIC_BP_FIELD
    diastolic_bp: int | None = _DIASTOLIC_BP_FIELD
    bmi: float | None = _BMI_FIELD
    has_diabetes: bool | None = None
    is_smoker: bool | None = None
    # None means altruistic/deceased -- poolable in cross-hospital search.
    # Set means this donor is only donating for that specific patient; see
    # the Donor model's docstring comment on this field.
    intended_recipient_id: uuid.UUID | None = None


class DonorUpdate(BaseModel):
    """blood_type/rh_factor are permanent once set (the compatibility
    engine and existing reports trust them), so they're deliberately absent
    here rather than editable. The clinical fields below are the opposite —
    expected to change over a donor's workup — so they're editable here
    like the rest of this schema.
    """

    full_name: str
    date_of_birth: date
    nic_number: str | None = None
    egfr: float | None = _EGFR_FIELD
    systolic_bp: int | None = _SYSTOLIC_BP_FIELD
    diastolic_bp: int | None = _DIASTOLIC_BP_FIELD
    bmi: float | None = _BMI_FIELD
    has_diabetes: bool | None = None
    is_smoker: bool | None = None
    intended_recipient_id: uuid.UUID | None = None


class DonorResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    full_name: str
    date_of_birth: date
    blood_type: BloodType
    rh_factor: RhFactor
    nic_number: str | None
    status: DonorStatus
    egfr: float | None
    systolic_bp: int | None
    diastolic_bp: int | None
    bmi: float | None
    has_diabetes: bool | None
    is_smoker: bool | None
    hla_typing_verified: bool
    intended_recipient_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DonorStatusUpdate(BaseModel):
    status: DonorStatus

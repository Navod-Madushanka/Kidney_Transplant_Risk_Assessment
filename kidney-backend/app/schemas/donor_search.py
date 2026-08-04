# app/schemas/donor_search.py
import uuid

from pydantic import BaseModel

from app.models.enums import BloodType, DonorStatus, RhFactor


class DonorCandidateResponse(BaseModel):
    """Deliberately slim — a candidate donor from another doctor's account.
    Never include full_name, date_of_birth, or nic_number here: those stay
    behind the owner-only /donors/{id} endpoint. Only enough is exposed to
    judge compatibility and coordinate with the owning doctor.
    """

    donor_id: uuid.UUID
    hospital_name: str
    doctor_full_name: str
    doctor_email: str
    blood_type: BloodType
    rh_factor: RhFactor
    status: DonorStatus
    abo_result: dict
    mismatch_result: dict

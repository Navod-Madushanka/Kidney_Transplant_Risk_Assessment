# app/schemas/pair.py
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.donor import DonorCreate, DonorResponse
from app.schemas.hla_typing import HLATypingEntry
from app.schemas.patient import PatientCreate, PatientResponse


class PairCrossmatchInput(BaseModel):
    t_cell_result: str | None = None
    b_cell_result: str | None = None
    interpretation: str | None = None
    remarks: str | None = None
    test_date: date | None = None


class PairOcrVerified(BaseModel):
    """None on either field = manual entry, trusted -- same contract as
    ocr_verified elsewhere (see hla_typing_service._resolve_verified).
    No crossmatch flag here: the crossmatch report's free-text fields are
    extracted in the same pass as the demographic fields (see
    PairRegistrationRequest.crossmatch), so `details` covers both; nothing
    downstream gates on a separate crossmatch-verified flag -- the real
    crossmatch gate is the doctor-entered is_positive on every compatibility
    check (see DonorPatientPair's docstring)."""

    details: bool | None = None
    hla_typing: bool | None = None


class PairRegistrationRequest(BaseModel):
    patient: PatientCreate
    donor: DonorCreate
    patient_hla: list[HLATypingEntry] = []
    donor_hla: list[HLATypingEntry] = []
    crossmatch: PairCrossmatchInput | None = None
    ocr_verified: PairOcrVerified | None = None


class PairResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    patient_id: uuid.UUID
    donor_id: uuid.UUID
    crossmatch_t_cell_result: str | None
    crossmatch_b_cell_result: str | None
    crossmatch_interpretation: str | None
    crossmatch_remarks: str | None
    crossmatch_test_date: date | None
    crossmatch_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PairDetailResponse(PairResponse):
    patient: PatientResponse
    donor: DonorResponse

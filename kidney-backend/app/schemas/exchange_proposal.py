# app/schemas/exchange_proposal.py
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ExchangeProposalPairDecision, ExchangeProposalStatus


class ExchangeProposalCreate(BaseModel):
    policy: str
    pair_ids: list[uuid.UUID]


class ExchangeProposalPairResponse(BaseModel):
    id: uuid.UUID
    proposal_id: uuid.UUID
    donor_id: uuid.UUID
    patient_id: uuid.UUID
    owning_doctor_id: uuid.UUID
    decision: ExchangeProposalPairDecision
    decided_at: datetime | None
    decided_by_doctor_id: uuid.UUID | None
    decline_reason: str | None
    is_open: bool


class ExchangeProposalResponse(BaseModel):
    id: uuid.UUID
    created_by_doctor_id: uuid.UUID
    policy: str
    weight: float
    status: ExchangeProposalStatus
    cycle_snapshot: dict
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    pairs: list[ExchangeProposalPairResponse]


class ExchangeProposalPairDecisionRequest(BaseModel):
    decision: ExchangeProposalPairDecision
    decline_reason: str | None = None

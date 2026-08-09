# app/schemas/exchange.py
import uuid

from pydantic import BaseModel

from app.models.enums import BloodType, RhFactor


class ExchangeNodeResponse(BaseModel):
    """One incompatible (donor, intended recipient) pair in the exchange
    pool. Deliberately slim for the other side's identity — same "no PII
    beyond blood type" precedent as DonorCandidateResponse
    (app/schemas/donor_search.py), extended here to the patient side too,
    since a cycle is meaningless without seeing who else is in it. Full
    names/DOB/NIC still stay behind the owner-only /patients and /donors
    endpoints.
    """

    pair_id: uuid.UUID
    donor_id: uuid.UUID
    donor_blood_type: BloodType
    donor_rh_factor: RhFactor
    donor_hospital_name: str
    donor_doctor_full_name: str
    donor_doctor_email: str
    patient_id: uuid.UUID
    patient_blood_type: BloodType
    patient_rh_factor: RhFactor
    patient_hospital_name: str
    patient_doctor_full_name: str
    patient_doctor_email: str


class ExchangeEdgeResponse(BaseModel):
    """A compatible directed donor -> recipient edge — pair_id's donor could
    give to pair_id's recipient. Only compatible edges exist in the graph at
    all (see exchange_graph_service.build_exchange_graph)."""

    from_pair_id: uuid.UUID
    to_pair_id: uuid.UUID
    mismatch_result: dict
    dsa_result: dict


class ExchangeCycleResponse(BaseModel):
    pair_ids: list[uuid.UUID]
    weight: float


class ExchangeMatchResponse(BaseModel):
    policy: str
    nodes: list[ExchangeNodeResponse]
    edges: list[ExchangeEdgeResponse]
    selected_cycles: list[ExchangeCycleResponse]

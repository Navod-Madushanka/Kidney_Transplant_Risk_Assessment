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
    # K9: "dialysis_start_date" when this patient's waiting-time credit
    # (equity_weighted policy, tie-break) is backed by a real dialysis
    # start date, "created_at_fallback" when it's the disclosed
    # registration-date proxy -- see exchange_matching_service.
    # uses_dialysis_start_date. Never let a coordinator mistake the proxy
    # for a fact.
    patient_wait_source: str


class ExchangeEdgeResponse(BaseModel):
    """A compatible directed donor -> recipient edge — pair_id's donor could
    give to pair_id's recipient. Only compatible edges exist in the graph at
    all (see exchange_graph_service.build_exchange_graph)."""

    from_pair_id: uuid.UUID
    to_pair_id: uuid.UUID
    mismatch_result: dict
    dsa_result: dict
    # None when this edge's donor/recipient are missing an LKDPI input --
    # see app/services/lkdpi_service.py. Only used by the max_lkdpi_quality
    # weight policy today; surfaced here so a coordinator can see why a
    # given edge did or didn't influence that policy's cycle selection.
    lkdpi_result: dict | None = None


class ExchangeCycleResponse(BaseModel):
    pair_ids: list[uuid.UUID]
    weight: float


class PairMatchExplanationResponse(BaseModel):
    """K7: why a pool pair isn't in any selected cycle. Only present for
    unmatched pairs -- see exchange_explanation_service.py. Aggregate counts
    only (never the underlying pairwise results) so the response stays O(n)
    in pool size regardless of how many ordered pairs were actually scored."""

    pair_id: uuid.UUID
    outbound_blocked: dict[str, int]
    inbound_blocked: dict[str, int]
    outbound_edges: int
    inbound_edges: int
    candidate_cycles: int
    verdict: str


class ExchangeMatchResponse(BaseModel):
    policy: str
    nodes: list[ExchangeNodeResponse]
    edges: list[ExchangeEdgeResponse]
    selected_cycles: list[ExchangeCycleResponse]
    explanations: list[PairMatchExplanationResponse]


class PolicyComparisonCycleResponse(BaseModel):
    """One candidate cycle that at least one policy selected. K8: instead of
    asking a coordinator to pick an optimization policy, show what all of
    them agree on -- a cycle every policy selects is robust, one only a
    single policy picks is a policy artefact."""

    pair_ids: list[uuid.UUID]
    weight_by_policy: dict[str, float]
    selected_by: list[str]


class ExchangeCompareResponse(BaseModel):
    policies: list[str]
    nodes: list[ExchangeNodeResponse]
    edges: list[ExchangeEdgeResponse]
    cycles: list[PolicyComparisonCycleResponse]


class HardToMatchPairResponse(BaseModel):
    """K9: one pool pair no policy selects under any weighting -- the
    desensitization/national-referral worklist. Reuses K7's verdict/blocked
    -reason counts and K8's cross-policy union rather than introducing a
    separate notion of "unmatched"."""

    node: ExchangeNodeResponse
    cpra_percentage: float | None
    wait_days: int
    verdict: str
    outbound_blocked: dict[str, int]
    inbound_blocked: dict[str, int]
    candidate_cycles: int


class HardToMatchResponse(BaseModel):
    pairs: list[HardToMatchPairResponse]

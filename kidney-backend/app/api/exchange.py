# app/api/exchange.py
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.exchange import (
    ExchangeCycleResponse,
    ExchangeEdgeResponse,
    ExchangeMatchResponse,
    ExchangeNodeResponse,
)
from app.services.audit_service import create_audit_log
from app.services.exchange_graph_service import build_exchange_graph, load_exchange_pool
from app.services.exchange_matching_service import WEIGHT_POLICIES, solve_exchange_matching

router = APIRouter(prefix="/exchange", tags=["exchange"])


@router.get("/match", response_model=ExchangeMatchResponse)
async def match_exchange_pool_endpoint(
    policy: str = Query("max_transplants"),
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Builds the current system-wide paired-exchange graph (every
    incompatible donor/intended-recipient pair — see
    exchange_graph_service.py) and returns the maximum-weight cycle packing
    under the requested policy. Read-only: running this never changes any
    donor/patient status (see exchange_matching_service.py's module
    docstring) — it's advisory, for a coordinator to act on manually.
    """
    if policy not in WEIGHT_POLICIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown policy '{policy}'. Choose one of: {sorted(WEIGHT_POLICIES)}",
        )

    pool = await load_exchange_pool(db)
    graph = build_exchange_graph(
        pool.nodes,
        pool.donor_typing_entries_by_donor,
        pool.patient_typing_entries_by_patient,
        pool.patient_antibodies_by_patient,
    )
    match_result = solve_exchange_matching(graph, policy, pool.patient_antibodies_by_patient)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="ran_exchange_matching",
        details={
            "policy": policy,
            "pool_size": len(pool.nodes),
            "selected_cycles": len(match_result.selected_cycles),
            "pairs_transplanted": sum(
                len(cycle.pair_ids) for cycle in match_result.selected_cycles
            ),
        },
    )

    return ExchangeMatchResponse(
        policy=policy,
        nodes=[
            ExchangeNodeResponse(
                pair_id=node.pair_id,
                donor_id=node.donor.id,
                donor_blood_type=node.donor.blood_type,
                donor_rh_factor=node.donor.rh_factor,
                donor_hospital_name=node.donor_hospital_name,
                donor_doctor_full_name=node.donor_doctor_full_name,
                donor_doctor_email=node.donor_doctor_email,
                patient_id=node.patient.id,
                patient_blood_type=node.patient.blood_type,
                patient_rh_factor=node.patient.rh_factor,
                patient_hospital_name=node.patient_hospital_name,
                patient_doctor_full_name=node.patient_doctor_full_name,
                patient_doctor_email=node.patient_doctor_email,
            )
            for node in graph.nodes
        ],
        edges=[
            ExchangeEdgeResponse(
                from_pair_id=edge.from_pair_id,
                to_pair_id=edge.to_pair_id,
                mismatch_result=asdict(edge.result.mismatch_result),
                dsa_result=asdict(edge.result.dsa_result),
            )
            for edge in graph.edges
        ],
        selected_cycles=[
            ExchangeCycleResponse(pair_ids=list(cycle.pair_ids), weight=cycle.weight)
            for cycle in match_result.selected_cycles
        ],
    )

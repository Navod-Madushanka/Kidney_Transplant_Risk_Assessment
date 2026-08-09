# app/api/exchange.py
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

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

    Deliberately not scoped to current_doctor (review #2 bug 25, confirmed
    intentional rather than an inherited-precedent oversight): a paired
    exchange only works at all if it can match across every participating
    hospital's pool, so "system-wide" is the actual point of this
    endpoint, not a gap. This follows the same convention
    donor_search_service.py already established for cross-hospital
    visibility -- don't restrict the query, instead put whose data it is
    directly in the response (see ExchangeNodeResponse's donor_doctor_email
    /patient_doctor_email fields below), so a doctor always sees who
    they'd actually be coordinating with.
    """
    if policy not in WEIGHT_POLICIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown policy '{policy}'. Choose one of: {sorted(WEIGHT_POLICIES)}",
        )

    # build_exchange_graph (O(n^2) pairwise scoring) and solve_exchange_matching
    # (cycle enumeration + a CBC subprocess) are both pure, synchronous CPU
    # work with no `await` inside -- run unchanged inside an `async def`
    # route handler, either one blocks the entire event loop (every other
    # request, including health checks) for its duration. Measured up to
    # ~5.6s combined at a 300-pair pool before this fix (review #2 bug 9).
    # run_in_threadpool offloads each to a worker thread so the loop stays
    # responsive; load_exchange_pool itself is already a normal awaited DB
    # call and doesn't need this.
    pool = await load_exchange_pool(db)
    graph = await run_in_threadpool(
        build_exchange_graph,
        pool.nodes,
        pool.donor_typing_entries_by_donor,
        pool.patient_typing_entries_by_patient,
        pool.patient_antibodies_by_patient,
    )
    match_result = await run_in_threadpool(
        solve_exchange_matching, graph, policy, pool.patient_antibodies_by_patient
    )

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

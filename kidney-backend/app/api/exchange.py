# app/api/exchange.py
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.exchange import (
    ExchangeCompareResponse,
    ExchangeCycleResponse,
    ExchangeEdgeResponse,
    ExchangeMatchResponse,
    ExchangeNodeResponse,
    HardToMatchPairResponse,
    HardToMatchResponse,
    PairMatchExplanationResponse,
    PolicyComparisonCycleResponse,
)
from app.services.audit_service import create_audit_log
from app.services.exchange_explanation_service import compute_pair_match_explanations
from app.services.exchange_graph_service import (
    ExchangeGraph,
    build_exchange_graph,
    load_exchange_pool,
)
from app.services.exchange_matching_service import (
    WEIGHT_POLICIES,
    SelectedCycle,
    build_graph_index,
    cpra_fraction,
    solve_exchange_matching,
    solve_exchange_matching_all_policies,
    uses_dialysis_start_date,
)
from app.services.exchange_matching_service import (
    wait_days as patient_wait_days,
)

router = APIRouter(prefix="/exchange", tags=["exchange"])


def _node_responses(graph: ExchangeGraph) -> list[ExchangeNodeResponse]:
    return [
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
            patient_wait_source=(
                "dialysis_start_date"
                if uses_dialysis_start_date(node.patient)
                else "created_at_fallback"
            ),
        )
        for node in graph.nodes
    ]


def _edge_responses(graph: ExchangeGraph) -> list[ExchangeEdgeResponse]:
    return [
        ExchangeEdgeResponse(
            from_pair_id=edge.from_pair_id,
            to_pair_id=edge.to_pair_id,
            mismatch_result=asdict(edge.result.mismatch_result),
            dsa_result=asdict(edge.result.dsa_result),
            lkdpi_result=(
                asdict(edge.result.lkdpi_result) if edge.result.lkdpi_result is not None else None
            ),
        )
        for edge in graph.edges
    ]


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
    explanations = compute_pair_match_explanations(
        graph, match_result.cycles, match_result.selected_cycles
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
        nodes=_node_responses(graph),
        edges=_edge_responses(graph),
        selected_cycles=[
            ExchangeCycleResponse(pair_ids=list(cycle.pair_ids), weight=cycle.weight)
            for cycle in match_result.selected_cycles
        ],
        explanations=[
            PairMatchExplanationResponse(
                pair_id=explanation.pair_id,
                outbound_blocked=explanation.outbound_blocked,
                inbound_blocked=explanation.inbound_blocked,
                outbound_edges=explanation.outbound_edges,
                inbound_edges=explanation.inbound_edges,
                candidate_cycles=explanation.candidate_cycles,
                verdict=explanation.verdict,
            )
            for explanation in explanations
        ],
    )


@router.get("/match/compare", response_model=ExchangeCompareResponse)
async def compare_exchange_policies_endpoint(
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """K8: solves every registered weight policy against the SAME pool/graph
    and returns the union of every policy's selected cycles, each tagged
    with which policies picked it (`selected_by`). A cycle every policy
    agrees on is robust; one only a single policy selects is a policy
    artefact -- this is the honest alternative to asking a coordinator to
    pick a policy from a dropdown they don't have the context to evaluate.

    Cycle enumeration and the GraphIndex are built once
    (solve_exchange_matching_all_policies) and reused across all four
    solves, so this costs roughly 1.3x a single /match call, not 4x -- see
    that function's docstring.
    """
    pool = await load_exchange_pool(db)
    graph = await run_in_threadpool(
        build_exchange_graph,
        pool.nodes,
        pool.donor_typing_entries_by_donor,
        pool.patient_typing_entries_by_patient,
        pool.patient_antibodies_by_patient,
    )
    results_by_policy = await run_in_threadpool(
        solve_exchange_matching_all_policies, graph, pool.patient_antibodies_by_patient
    )

    # Keyed by the cycle's own pair_ids tuple: every policy here solved
    # against the exact same shared `cycles` list (see
    # solve_exchange_matching_all_policies), so identical tuples really are
    # the same candidate cycle, not just a coincidental pair_id overlap.
    cycles_by_pair_ids: dict[tuple, dict] = {}
    for policy_name, result in results_by_policy.items():
        for selected in result.selected_cycles:
            key = tuple(selected.pair_ids)
            entry = cycles_by_pair_ids.setdefault(
                key, {"pair_ids": key, "weight_by_policy": {}, "selected_by": []}
            )
            entry["weight_by_policy"][policy_name] = selected.weight
            entry["selected_by"].append(policy_name)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="compared_exchange_policies",
        details={
            "pool_size": len(pool.nodes),
            "policies": sorted(WEIGHT_POLICIES),
            "cycles_selected_by_any_policy": len(cycles_by_pair_ids),
        },
    )

    return ExchangeCompareResponse(
        policies=sorted(WEIGHT_POLICIES),
        nodes=_node_responses(graph),
        edges=_edge_responses(graph),
        cycles=[
            PolicyComparisonCycleResponse(
                pair_ids=list(entry["pair_ids"]),
                weight_by_policy=entry["weight_by_policy"],
                selected_by=entry["selected_by"],
            )
            for entry in cycles_by_pair_ids.values()
        ],
    )


@router.get("/hard-to-match", response_model=HardToMatchResponse)
async def hard_to_match_endpoint(
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """K9: the desensitisation/national-referral worklist -- pool pairs that
    NO registered policy selects, under any weighting. Reuses K8's cross-
    policy solve rather than introducing a separate notion of "unmatched":
    a pair absent from every policy's selected set is genuinely hard to
    match, not just an artefact of one policy's particular weights.

    Also reuses K7's per-pair explanation (compute_pair_match_explanations)
    by feeding it the UNION of every policy's selected cycles as the
    "selected" set -- so a pair only ends up on this worklist if it's
    unmatched everywhere, and its verdict/blocked-reason counts come from
    the exact same computation the single-policy view uses, not a
    parallel one.

    Sorted by real waiting time, longest first.
    """
    pool = await load_exchange_pool(db)
    graph = await run_in_threadpool(
        build_exchange_graph,
        pool.nodes,
        pool.donor_typing_entries_by_donor,
        pool.patient_typing_entries_by_patient,
        pool.patient_antibodies_by_patient,
    )
    results_by_policy = await run_in_threadpool(
        solve_exchange_matching_all_policies, graph, pool.patient_antibodies_by_patient
    )

    # Every policy here solved against the same shared `cycles` list (see
    # solve_exchange_matching_all_policies) -- any one result's `cycles` is
    # every candidate, not just what that particular policy selected.
    cycles = next(iter(results_by_policy.values())).cycles
    union_selected: dict[tuple, SelectedCycle] = {
        tuple(selected.pair_ids): selected
        for result in results_by_policy.values()
        for selected in result.selected_cycles
    }
    explanations = compute_pair_match_explanations(graph, cycles, list(union_selected.values()))

    index = build_graph_index(graph, pool.patient_antibodies_by_patient)
    node_by_pair_id = {node.pair_id: node for node in graph.nodes}
    node_response_by_pair_id = {response.pair_id: response for response in _node_responses(graph)}

    pairs = [
        HardToMatchPairResponse(
            node=node_response_by_pair_id[explanation.pair_id],
            cpra_percentage=round(
                cpra_fraction(node_by_pair_id[explanation.pair_id].patient.id, index) * 100, 1
            ),
            wait_days=patient_wait_days(node_by_pair_id[explanation.pair_id].patient),
            verdict=explanation.verdict,
            outbound_blocked=explanation.outbound_blocked,
            inbound_blocked=explanation.inbound_blocked,
            candidate_cycles=explanation.candidate_cycles,
        )
        for explanation in explanations
    ]
    pairs.sort(key=lambda pair: pair.wait_days, reverse=True)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="viewed_hard_to_match_worklist",
        details={"pool_size": len(pool.nodes), "hard_to_match_count": len(pairs)},
    )

    return HardToMatchResponse(pairs=pairs)

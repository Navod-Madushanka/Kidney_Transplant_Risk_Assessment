# app/api/exchange_proposals.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.enums import ExchangeProposalPairDecision, ExchangeProposalStatus
from app.models.exchange_proposal import ExchangeProposal
from app.models.exchange_proposal_pair import ExchangeProposalPair
from app.schemas.exchange_proposal import (
    ExchangeProposalCreate,
    ExchangeProposalPairDecisionRequest,
    ExchangeProposalPairResponse,
    ExchangeProposalResponse,
)
from app.services.audit_service import create_audit_log
from app.services.exchange_graph_service import build_exchange_graph, load_exchange_pool
from app.services.exchange_matching_service import (
    WEIGHT_POLICIES,
    build_graph_index,
    solve_exchange_matching,
)
from app.services.exchange_proposal_service import (
    ExchangeProposalConflict,
    IllegalExchangeProposalPairDecision,
    IllegalExchangeProposalTransition,
    cancel_proposal,
    create_proposal,
    decide_pair,
    expire_if_due,
    get_pair_by_id,
    get_proposal_by_id,
    get_proposal_pairs,
    list_open_proposals,
    list_proposals_pending_for_doctor,
)

router = APIRouter(prefix="/exchange/proposals", tags=["exchange-proposals"])


def _proposal_response(
    proposal: ExchangeProposal, pairs: list[ExchangeProposalPair]
) -> ExchangeProposalResponse:
    return ExchangeProposalResponse(
        id=proposal.id,
        created_by_doctor_id=proposal.created_by_doctor_id,
        policy=proposal.policy,
        weight=proposal.weight,
        status=proposal.status,
        cycle_snapshot=proposal.cycle_snapshot,
        expires_at=proposal.expires_at,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        pairs=[
            ExchangeProposalPairResponse(
                id=pair.id,
                proposal_id=pair.proposal_id,
                donor_id=pair.donor_id,
                patient_id=pair.patient_id,
                owning_doctor_id=pair.owning_doctor_id,
                decision=pair.decision,
                decided_at=pair.decided_at,
                decided_by_doctor_id=pair.decided_by_doctor_id,
                decline_reason=pair.decline_reason,
                is_open=pair.is_open,
            )
            for pair in pairs
        ],
    )


async def _expire_if_due_and_audit(
    db: AsyncSession, doctor_id: uuid.UUID, proposal: ExchangeProposal
) -> ExchangeProposal:
    """Lazy expiry (K6) wrapped with an audit entry attributed to the
    doctor whose read happened to surface it -- the pure startup sweep
    (exchange_proposal_service.sweep_expired_proposals) has no doctor in
    context and deliberately does NOT audit-log, since AuditLog.doctor_id
    is a required column with no "system actor" concept in this data
    model. This is the one place a real doctor's read triggers the same
    state change, so it's the one place that can honestly attribute it."""
    was_proposed = proposal.status == ExchangeProposalStatus.PROPOSED
    proposal = await expire_if_due(db, proposal, commit=False)
    if was_proposed and proposal.status == ExchangeProposalStatus.EXPIRED:
        await create_audit_log(
            db,
            doctor_id=doctor_id,
            action="expired_exchange_cycle",
            details={"proposal_id": str(proposal.id)},
            commit=False,
        )
    await db.commit()
    return proposal


@router.post("", response_model=ExchangeProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_proposal_endpoint(
    payload: ExchangeProposalCreate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """K5: proposes a discovered cycle for commitment. Never trusts the
    client-supplied cycle -- re-runs the match server-side and verifies
    `pair_ids` is actually in the current selected set for `policy` before
    creating anything. 409s (naming the conflicting proposal) if any pair
    is already part of a different open proposal -- see
    exchange_proposal_service's module docstring for the invariant this
    enforces."""
    if payload.policy not in WEIGHT_POLICIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown policy '{payload.policy}'. Choose one of: {sorted(WEIGHT_POLICIES)}",
        )

    pool = await load_exchange_pool(db)
    graph = await run_in_threadpool(
        build_exchange_graph,
        pool.nodes,
        pool.donor_typing_entries_by_donor,
        pool.patient_typing_entries_by_patient,
        pool.patient_antibodies_by_patient,
    )
    match_result = await run_in_threadpool(
        solve_exchange_matching, graph, payload.policy, pool.patient_antibodies_by_patient
    )

    submitted = frozenset(payload.pair_ids)
    selected = next(
        (cycle for cycle in match_result.selected_cycles if frozenset(cycle.pair_ids) == submitted),
        None,
    )
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The submitted cycle is not in the current selected set for this policy -- "
                "the pool may have changed. Re-run the match and try again."
            ),
        )

    index = build_graph_index(graph, pool.patient_antibodies_by_patient)

    try:
        proposal = await create_proposal(
            db,
            current_doctor.id,
            payload.policy,
            selected.pair_ids,
            selected.weight,
            index,
            commit=False,
        )
    except ExchangeProposalConflict as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{exc}. Cancel the conflicting proposal first, or wait for it to resolve.",
        )
    except IntegrityError:
        # Defense-in-depth against the same race the advisory lock in
        # create_proposal already closes off under normal operation -- see
        # that function's docstring. Should not be reachable in practice.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One of these pairs was just committed to a different proposal. Re-run the match and try again.",
        )

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="proposed_exchange_cycle",
        details={
            "proposal_id": str(proposal.id),
            "policy": payload.policy,
            "pair_ids": [str(pair_id) for pair_id in selected.pair_ids],
            "weight": selected.weight,
        },
        commit=False,
    )
    await db.commit()

    pairs = await get_proposal_pairs(db, proposal.id)
    return _proposal_response(proposal, pairs)


@router.get("", response_model=list[ExchangeProposalResponse])
async def list_proposals_endpoint(
    mine: bool = Query(False),
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """`mine=true`: the pending-decisions inbox -- open proposals with at
    least one pair the calling doctor owns and hasn't decided yet.
    Unfiltered: every open proposal system-wide, since exchange is
    cross-hospital by nature (same convention GET /exchange/match uses --
    see that endpoint's docstring)."""
    if mine:
        proposals = await list_proposals_pending_for_doctor(db, current_doctor.id)
    else:
        proposals = await list_open_proposals(db)

    responses = []
    for proposal in proposals:
        proposal = await _expire_if_due_and_audit(db, current_doctor.id, proposal)
        pairs = await get_proposal_pairs(db, proposal.id)
        responses.append(_proposal_response(proposal, pairs))
    return responses


@router.get("/{proposal_id}", response_model=ExchangeProposalResponse)
async def get_proposal_endpoint(
    proposal_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deliberately NOT owner-scoped, unlike get_donor_by_id_for_doctor --
    every participant in a proposal (both sides of every pair) must be
    able to see the whole cycle they're part of, not just their own
    hospital's leg of it."""
    proposal = await get_proposal_by_id(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    proposal = await _expire_if_due_and_audit(db, current_doctor.id, proposal)
    pairs = await get_proposal_pairs(db, proposal.id)
    return _proposal_response(proposal, pairs)


@router.post(
    "/{proposal_id}/pairs/{pair_id}/decision", response_model=ExchangeProposalResponse
)
async def decide_pair_endpoint(
    proposal_id: uuid.UUID,
    pair_id: uuid.UUID,
    payload: ExchangeProposalPairDecisionRequest,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owning-doctor only (403 otherwise) -- see ExchangeProposalPair.
    owning_doctor_id's docstring for why it's the donor's doctor, not the
    recipient's. On the last acceptance in the cycle: the parent locks
    (ACCEPTED) and every donor reserves. On any decline: the parent
    declines and any reservation releases."""
    if payload.decision == ExchangeProposalPairDecision.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="decision must be 'accepted' or 'declined'",
        )

    proposal = await get_proposal_by_id(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    pair = await get_pair_by_id(db, proposal_id, pair_id)
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pair not found")

    if pair.owning_doctor_id != current_doctor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the pair's owning doctor may record a decision on it",
        )

    try:
        proposal = await decide_pair(
            db,
            proposal,
            pair,
            payload.decision,
            current_doctor.id,
            decline_reason=payload.decline_reason,
            commit=False,
        )
    except IllegalExchangeProposalPairDecision as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    action = (
        "accepted_exchange_pair"
        if payload.decision == ExchangeProposalPairDecision.ACCEPTED
        else "declined_exchange_pair"
    )
    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action=action,
        donor_id=pair.donor_id,
        patient_id=pair.patient_id,
        details={
            "proposal_id": str(proposal.id),
            "pair_id": str(pair.id),
            "decision": payload.decision.value,
        },
        commit=False,
    )
    if proposal.status == ExchangeProposalStatus.ACCEPTED:
        await create_audit_log(
            db,
            doctor_id=current_doctor.id,
            action="locked_exchange_cycle",
            details={"proposal_id": str(proposal.id)},
            commit=False,
        )
    await db.commit()

    pairs = await get_proposal_pairs(db, proposal.id)
    return _proposal_response(proposal, pairs)


@router.post("/{proposal_id}/cancel", response_model=ExchangeProposalResponse)
async def cancel_proposal_endpoint(
    proposal_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The proposer or an admin only -- never the owning doctor of just one
    pair, and never on another doctor's behalf. Releases any reserved
    donors (a no-op if the proposal hadn't been fully accepted yet)."""
    proposal = await get_proposal_by_id(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    if proposal.created_by_doctor_id != current_doctor.id and not current_doctor.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the proposer or an admin may cancel this proposal",
        )

    try:
        proposal = await cancel_proposal(db, proposal, commit=False)
    except IllegalExchangeProposalTransition as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="cancelled_exchange_cycle",
        details={"proposal_id": str(proposal.id)},
        commit=False,
    )
    await db.commit()

    pairs = await get_proposal_pairs(db, proposal.id)
    return _proposal_response(proposal, pairs)

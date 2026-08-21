# app/services/exchange_proposal_service.py
"""
The paired-exchange commitment workflow (Part K, K2-K6): turning a
discovered cycle (exchange_matching_service.SelectedCycle) into something a
doctor can actually act on, with a Postgres-enforced guarantee that a donor
never ends up double-committed across two proposals.

**Exactly one function writes ExchangeProposal.status: transition_proposal_
status.** It folds every child ExchangeProposalPair.is_open update into the
same transaction as the parent's status change, so is_open always mirrors
"is this proposal still PROPOSED or ACCEPTED" by construction. Every other
function in this module that changes a proposal's status (create_proposal
sets the initial PROPOSED row directly via ORM insert, not a transition;
decide_pair, cancel_proposal, expire_if_due, sweep_expired_proposals all
call transition_proposal_status) goes through it -- do not set
proposal.status directly anywhere else in this codebase.

The overlap invariant itself -- a donor may be in at most one OPEN proposal
system-wide -- is a partial unique index on exchange_proposal_pairs(donor_id)
WHERE is_open (see that model's __table_args__), not application code alone.
create_proposal's pre-check (under a Postgres advisory lock, same pattern
audit_service.create_audit_log uses for its hash chain) is the friendly
error message; the index is the actual guarantee.
"""
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.enums import DonorStatus, ExchangeProposalPairDecision, ExchangeProposalStatus
from app.models.exchange_proposal import ExchangeProposal
from app.models.exchange_proposal_pair import ExchangeProposalPair
from app.reference_data.dsa_threshold import DSA_HALTING_SEVERITY, DSA_SEVERITY_BANDS
from app.reference_data.hla_antigen_frequencies import HLA_FREQUENCY_TABLE_VERSION
from app.services.donor_service import IllegalDonorStatusTransition, update_donor_status
from app.services.exchange_matching_service import Cycle, GraphIndex, _cycle_edges

# Arbitrary fixed key for a Postgres advisory lock scoped to proposal
# creation -- distinct from audit_service's _AUDIT_CHAIN_LOCK_KEY so the two
# don't contend with each other for unrelated reasons. Serializes concurrent
# creations over potentially-overlapping cycles so the second one's
# pre-check SELECT reliably sees the first's already-committed row (see
# create_proposal), rather than racing to the unique index.
_PROPOSAL_CREATION_LOCK_KEY = 4917326805

DEFAULT_EXPIRY_DAYS = 7

_ALLOWED_TRANSITIONS: dict[ExchangeProposalStatus, set[ExchangeProposalStatus]] = {
    ExchangeProposalStatus.PROPOSED: {
        ExchangeProposalStatus.ACCEPTED,
        ExchangeProposalStatus.DECLINED,
        ExchangeProposalStatus.EXPIRED,
        ExchangeProposalStatus.CANCELLED,
    },
    ExchangeProposalStatus.ACCEPTED: {
        ExchangeProposalStatus.COMPLETED,
        ExchangeProposalStatus.CANCELLED,
    },
    ExchangeProposalStatus.DECLINED: set(),
    ExchangeProposalStatus.EXPIRED: set(),
    ExchangeProposalStatus.CANCELLED: set(),
    ExchangeProposalStatus.COMPLETED: set(),
}


class IllegalExchangeProposalTransition(Exception):
    """Raised by transition_proposal_status when `status` isn't reachable
    from the proposal's current status -- see _ALLOWED_TRANSITIONS."""

    def __init__(self, current: ExchangeProposalStatus, requested: ExchangeProposalStatus):
        self.current = current
        self.requested = requested
        super().__init__(
            f"Cannot transition exchange proposal status from {current.value!r} "
            f"to {requested.value!r}"
        )


class ExchangeProposalConflict(Exception):
    """Raised by create_proposal when a pair's donor is already part of a
    different open proposal -- the API layer catches this (and a raw
    IntegrityError, belt-and-braces against the same race the advisory lock
    is meant to close off) and responds 409, naming the conflicting
    proposal."""

    def __init__(self, donor_id: uuid.UUID, conflicting_proposal_id: uuid.UUID):
        self.donor_id = donor_id
        self.conflicting_proposal_id = conflicting_proposal_id
        super().__init__(
            f"Donor {donor_id} is already part of open proposal {conflicting_proposal_id}"
        )


class IllegalExchangeProposalPairDecision(Exception):
    """Raised by decide_pair when a decision can't be recorded -- the
    proposal isn't PROPOSED, the pair already has a decision, or the caller
    doesn't own the pair. The API layer maps this to 409/403 as
    appropriate."""


async def transition_proposal_status(
    db: AsyncSession,
    proposal: ExchangeProposal,
    status: ExchangeProposalStatus,
    commit: bool = True,
) -> ExchangeProposal:
    """The ONLY function allowed to write ExchangeProposal.status -- see
    module docstring. commit=False lets a caller fold this into a larger
    transaction (donor reservation/release, an audit log entry), same
    contract as donor_service.update_donor_status's commit param."""
    if status != proposal.status and status not in _ALLOWED_TRANSITIONS[proposal.status]:
        raise IllegalExchangeProposalTransition(proposal.status, status)

    proposal.status = status
    is_open = status in (ExchangeProposalStatus.PROPOSED, ExchangeProposalStatus.ACCEPTED)
    await db.execute(
        update(ExchangeProposalPair)
        .where(ExchangeProposalPair.proposal_id == proposal.id)
        .values(is_open=is_open)
    )

    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(proposal)
    return proposal


def build_cycle_snapshot(index: GraphIndex, pair_ids: Cycle) -> dict:
    """K2: freezes the clinical picture for one proposed cycle at proposal
    time, mirroring MatchReport's JSONB-snapshot convention (asdict() the
    already-computed dataclasses straight into JSON, plus the reference-
    data versions in force) rather than a separate version table -- see
    MatchReport's own docstring for why. A proposal accepted later must
    show the clinical picture it was proposed with, not a re-run against a
    pool that's since changed. Only the cycle's own nodes/edges are
    captured, not the whole pool.
    """
    nodes = []
    for pair_id in pair_ids:
        node = index.node_by_id[pair_id]
        nodes.append(
            {
                "pair_id": str(pair_id),
                "donor_id": str(node.donor.id),
                "donor_blood_type": node.donor.blood_type.value,
                "donor_hospital_name": node.donor_hospital_name,
                "donor_doctor_full_name": node.donor_doctor_full_name,
                "donor_doctor_email": node.donor_doctor_email,
                "patient_id": str(node.patient.id),
                "patient_blood_type": node.patient.blood_type.value,
                "patient_hospital_name": node.patient_hospital_name,
                "patient_doctor_full_name": node.patient_doctor_full_name,
                "patient_doctor_email": node.patient_doctor_email,
            }
        )

    edges = []
    cycle_edges = _cycle_edges(pair_ids, index.edge_by_pair)
    for edge in cycle_edges:
        edges.append(
            {
                "from_pair_id": str(edge.from_pair_id),
                "to_pair_id": str(edge.to_pair_id),
                "mismatch_result": asdict(edge.result.mismatch_result),
                "dsa_result": asdict(edge.result.dsa_result),
                "lkdpi_result": (
                    asdict(edge.result.lkdpi_result)
                    if edge.result.lkdpi_result is not None
                    else None
                ),
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "hla_frequency_table_version": HLA_FREQUENCY_TABLE_VERSION,
        "dsa_halting_severity": DSA_HALTING_SEVERITY,
        "dsa_bands": [
            {
                "name": band.name,
                "min_mfi": band.min_mfi,
                "max_mfi": band.max_mfi if band.max_mfi != float("inf") else None,
            }
            for band in DSA_SEVERITY_BANDS
        ],
    }


async def create_proposal(
    db: AsyncSession,
    created_by_doctor_id: uuid.UUID,
    policy: str,
    pair_ids: Cycle,
    weight: float,
    graph_index: GraphIndex,
    commit: bool = True,
) -> ExchangeProposal:
    """K2/K3: creates a proposal and one ExchangeProposalPair per pair_id,
    under a Postgres advisory lock (see _PROPOSAL_CREATION_LOCK_KEY).

    Never trusts a client-supplied cycle itself -- the caller (the API
    endpoint) must already have re-solved the match server-side and
    verified `pair_ids` is genuinely in the current selected set BEFORE
    calling this. `graph_index` must be built from that same fresh solve,
    so every node/donor/patient referenced below is real and current.

    Raises ExchangeProposalConflict if any pair's donor is already part of
    a different open proposal.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": _PROPOSAL_CREATION_LOCK_KEY}
    )

    donor_ids = list(pair_ids)
    conflict_result = await db.execute(
        select(ExchangeProposalPair).where(
            ExchangeProposalPair.donor_id.in_(donor_ids),
            ExchangeProposalPair.is_open.is_(True),
        )
    )
    conflicting_pair = conflict_result.scalars().first()
    if conflicting_pair is not None:
        raise ExchangeProposalConflict(conflicting_pair.donor_id, conflicting_pair.proposal_id)

    snapshot = build_cycle_snapshot(graph_index, pair_ids)
    expires_at = datetime.now(timezone.utc) + timedelta(days=DEFAULT_EXPIRY_DAYS)

    proposal = ExchangeProposal(
        created_by_doctor_id=created_by_doctor_id,
        policy=policy,
        weight=weight,
        cycle_snapshot=snapshot,
        expires_at=expires_at,
    )
    db.add(proposal)
    await db.flush()

    for pair_id in pair_ids:
        node = graph_index.node_by_id[pair_id]
        db.add(
            ExchangeProposalPair(
                proposal_id=proposal.id,
                donor_id=node.donor.id,
                patient_id=node.patient.id,
                owning_doctor_id=node.donor.doctor_id,
            )
        )

    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(proposal)
    return proposal


async def _cycle_donor_ids(db: AsyncSession, proposal_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(ExchangeProposalPair.donor_id).where(ExchangeProposalPair.proposal_id == proposal_id)
    )
    return [row[0] for row in result.all()]


async def _reserve_cycle_donors(db: AsyncSession, proposal_id: uuid.UUID) -> None:
    """K4: AVAILABLE -> RESERVED for every donor in the cycle, fired only
    on full acceptance (see decide_pair). Folded into the caller's
    transaction -- always called with commit deferred to the caller."""
    donor_ids = await _cycle_donor_ids(db, proposal_id)
    result = await db.execute(select(Donor).where(Donor.id.in_(donor_ids)))
    for donor in result.scalars().all():
        try:
            await update_donor_status(db, donor, DonorStatus.RESERVED, commit=False)
        except IllegalDonorStatusTransition:
            # This donor moved to a terminal/other status out-of-band (e.g.
            # TRANSPLANTED via a direct match, MEDICALLY_UNFIT) since the
            # cycle was proposed. The proposal/pair bookkeeping still
            # proceeds -- it's not this function's job to force a donor
            # back into a status that no longer reflects reality.
            pass


async def _release_cycle_donors(db: AsyncSession, proposal_id: uuid.UUID) -> None:
    """K4: RESERVED -> AVAILABLE for any donor this proposal reserved,
    fired on decline, cancel, or expiry. A no-op for donors that were
    never reserved (e.g. a decline before any acceptance) -- only donors
    currently RESERVED are touched."""
    donor_ids = await _cycle_donor_ids(db, proposal_id)
    result = await db.execute(
        select(Donor).where(Donor.id.in_(donor_ids), Donor.status == DonorStatus.RESERVED)
    )
    for donor in result.scalars().all():
        await update_donor_status(db, donor, DonorStatus.AVAILABLE, commit=False)


async def decide_pair(
    db: AsyncSession,
    proposal: ExchangeProposal,
    pair: ExchangeProposalPair,
    decision: ExchangeProposalPairDecision,
    decided_by_doctor_id: uuid.UUID,
    decline_reason: str | None = None,
    commit: bool = True,
) -> ExchangeProposal:
    """K5: records one pair's accept/decline. On the LAST acceptance (every
    pair in the proposal now accepted): transitions the parent to ACCEPTED
    and reserves every donor in the cycle. On ANY decline: transitions the
    parent to DECLINED and releases every donor this proposal reserved (see
    _release_cycle_donors -- a no-op here in practice, since donors are
    only ever reserved on full acceptance, but kept for symmetry with
    cancel/expire, which share this same release call after a proposal may
    already be ACCEPTED).

    The caller (API layer) is expected to have already checked
    `decided_by_doctor_id == pair.owning_doctor_id` (403 otherwise) --
    this function re-checks defensively so a stale in-memory pair passed
    by a caller that raced with another decision can't corrupt state.
    """
    if proposal.status != ExchangeProposalStatus.PROPOSED:
        raise IllegalExchangeProposalPairDecision(
            f"Proposal {proposal.id} is {proposal.status.value!r}, not accepting decisions"
        )
    if pair.decision != ExchangeProposalPairDecision.PENDING:
        raise IllegalExchangeProposalPairDecision(
            f"Pair {pair.id} already has a decision ({pair.decision.value!r})"
        )
    if pair.owning_doctor_id != decided_by_doctor_id:
        raise IllegalExchangeProposalPairDecision(
            "Only the pair's owning doctor may record a decision on it"
        )

    pair.decision = decision
    pair.decided_at = datetime.now(timezone.utc)
    pair.decided_by_doctor_id = decided_by_doctor_id
    pair.decline_reason = decline_reason
    await db.flush()

    if decision == ExchangeProposalPairDecision.DECLINED:
        await transition_proposal_status(
            db, proposal, ExchangeProposalStatus.DECLINED, commit=False
        )
        await _release_cycle_donors(db, proposal.id)
    else:
        remaining = await db.execute(
            select(func.count())
            .select_from(ExchangeProposalPair)
            .where(
                ExchangeProposalPair.proposal_id == proposal.id,
                ExchangeProposalPair.decision == ExchangeProposalPairDecision.PENDING,
            )
        )
        if remaining.scalar_one() == 0:
            await transition_proposal_status(
                db, proposal, ExchangeProposalStatus.ACCEPTED, commit=False
            )
            await _reserve_cycle_donors(db, proposal.id)

    if commit:
        await db.commit()
    await db.refresh(proposal)
    return proposal


async def cancel_proposal(
    db: AsyncSession, proposal: ExchangeProposal, commit: bool = True
) -> ExchangeProposal:
    """K5: proposer or admin only (API layer's job to check). Legal from
    PROPOSED or ACCEPTED -- releases any reserved donors either way."""
    await transition_proposal_status(db, proposal, ExchangeProposalStatus.CANCELLED, commit=False)
    await _release_cycle_donors(db, proposal.id)
    if commit:
        await db.commit()
    await db.refresh(proposal)
    return proposal


async def expire_if_due(
    db: AsyncSession, proposal: ExchangeProposal, commit: bool = True
) -> ExchangeProposal:
    """K6: lazy expiry check, called on every read path (GET
    /exchange/proposals, GET /exchange/proposals/{id}) -- a PROPOSED row
    past its expires_at is reported as EXPIRED and its pairs released on
    next access. See sweep_expired_proposals for the startup-sweep half of
    the belt-and-braces approach (mirrors Part G's spool-cleanup pattern:
    no scheduler in this codebase, so lazy-on-read + a startup sweep is the
    whole mechanism)."""
    if (
        proposal.status == ExchangeProposalStatus.PROPOSED
        and proposal.expires_at < datetime.now(timezone.utc)
    ):
        await transition_proposal_status(db, proposal, ExchangeProposalStatus.EXPIRED, commit=False)
        await _release_cycle_donors(db, proposal.id)
        if commit:
            await db.commit()
        await db.refresh(proposal)
    return proposal


async def sweep_expired_proposals(db: AsyncSession) -> int:
    """Startup sweep (see app/main.py's lifespan hook) -- catches proposals
    that expired while the server was down. Returns the number expired."""
    result = await db.execute(
        select(ExchangeProposal).where(
            ExchangeProposal.status == ExchangeProposalStatus.PROPOSED,
            ExchangeProposal.expires_at < datetime.now(timezone.utc),
        )
    )
    expired_proposals = list(result.scalars().all())
    for proposal in expired_proposals:
        await transition_proposal_status(db, proposal, ExchangeProposalStatus.EXPIRED, commit=False)
        await _release_cycle_donors(db, proposal.id)
    if expired_proposals:
        await db.commit()
    return len(expired_proposals)


async def get_proposal_by_id(db: AsyncSession, proposal_id: uuid.UUID) -> ExchangeProposal | None:
    result = await db.execute(select(ExchangeProposal).where(ExchangeProposal.id == proposal_id))
    return result.scalar_one_or_none()


async def get_proposal_pairs(
    db: AsyncSession, proposal_id: uuid.UUID
) -> list[ExchangeProposalPair]:
    result = await db.execute(
        select(ExchangeProposalPair)
        .where(ExchangeProposalPair.proposal_id == proposal_id)
        .order_by(ExchangeProposalPair.created_at)
    )
    return list(result.scalars().all())


async def get_pair_by_id(
    db: AsyncSession, proposal_id: uuid.UUID, pair_id: uuid.UUID
) -> ExchangeProposalPair | None:
    result = await db.execute(
        select(ExchangeProposalPair).where(
            ExchangeProposalPair.id == pair_id, ExchangeProposalPair.proposal_id == proposal_id
        )
    )
    return result.scalar_one_or_none()


async def list_open_proposals(db: AsyncSession) -> list[ExchangeProposal]:
    """Every open (PROPOSED/ACCEPTED) proposal, cross-hospital by nature --
    matches /exchange/match's own "system-wide, not doctor-scoped"
    convention (see that endpoint's docstring): every participant in a
    proposal must be able to see the whole cycle they're part of."""
    result = await db.execute(
        select(ExchangeProposal)
        .where(
            ExchangeProposal.status.in_(
                [ExchangeProposalStatus.PROPOSED, ExchangeProposalStatus.ACCEPTED]
            )
        )
        .order_by(ExchangeProposal.created_at.desc())
    )
    return list(result.scalars().all())


async def list_proposals_pending_for_doctor(
    db: AsyncSession, doctor_id: uuid.UUID
) -> list[ExchangeProposal]:
    """?mine=true's pending-decisions inbox: every open proposal with at
    least one pair this doctor owns and hasn't decided yet. One indexed
    query thanks to owning_doctor_id being denormalised onto the pair row
    (see that column's docstring)."""
    result = await db.execute(
        select(ExchangeProposal)
        .join(ExchangeProposalPair, ExchangeProposalPair.proposal_id == ExchangeProposal.id)
        .where(
            ExchangeProposalPair.owning_doctor_id == doctor_id,
            ExchangeProposalPair.decision == ExchangeProposalPairDecision.PENDING,
            ExchangeProposalPair.is_open.is_(True),
        )
        .distinct()
        .order_by(ExchangeProposal.created_at.desc())
    )
    return list(result.scalars().all())

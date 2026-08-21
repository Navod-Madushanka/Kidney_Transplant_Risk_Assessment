# app/tests/integration/test_exchange_proposal_service.py
"""
Service-level coverage for exchange_proposal_service.py that doesn't map
cleanly onto one HTTP endpoint: the state machine's full transition matrix
(including COMPLETED, which no endpoint reaches yet -- see the module
docstring), the overlap invariant enforced at the DATABASE level (bypassing
create_proposal's own pre-check, per K13's explicit "test with the
application check bypassed"), snapshot immutability, and expiry. HTTP-level
behavior (authorization, the create/decision/cancel endpoints, the
concurrent-creation race) is in test_exchange_proposals_api.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.donor import Donor
from app.models.enums import (
    DonorStatus,
    ExchangeProposalStatus,
)
from app.models.exchange_proposal import ExchangeProposal
from app.models.exchange_proposal_pair import ExchangeProposalPair
from app.services.exchange_proposal_service import (
    IllegalExchangeProposalTransition,
    expire_if_due,
    sweep_expired_proposals,
    transition_proposal_status,
)
from app.tests.conftest import create_donor, create_patient

MATCHING_TYPING = [
    {"locus": "A", "allele_1": "01", "allele_2": "02"},
    {"locus": "B", "allele_1": "07", "allele_2": "08"},
    {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
]


async def _doctor_id(client: AsyncClient) -> uuid.UUID:
    response = await client.get("/auth/me")
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])


async def _make_bare_proposal(
    db_session,
    auth_client: AsyncClient,
    second_auth_client: AsyncClient,
    *,
    status: ExchangeProposalStatus = ExchangeProposalStatus.PROPOSED,
    expires_at: datetime | None = None,
) -> ExchangeProposal:
    """A minimal, directly-constructed proposal (bypassing create_proposal
    entirely) over one real donor/patient pair -- for tests about the state
    machine or expiry mechanics, not the creation flow itself."""
    patient = await create_patient(auth_client, blood_type="A")
    donor = await create_donor(auth_client, blood_type="B", intended_recipient_id=patient["id"])
    owning_doctor_id = await _doctor_id(auth_client)
    proposer_id = await _doctor_id(second_auth_client)

    proposal = ExchangeProposal(
        created_by_doctor_id=proposer_id,
        policy="max_transplants",
        weight=1.0,
        status=status,
        cycle_snapshot={"nodes": [], "edges": []},
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=7)),
    )
    db_session.add(proposal)
    await db_session.flush()

    is_open = status in (ExchangeProposalStatus.PROPOSED, ExchangeProposalStatus.ACCEPTED)
    pair = ExchangeProposalPair(
        proposal_id=proposal.id,
        donor_id=uuid.UUID(donor["id"]),
        patient_id=uuid.UUID(patient["id"]),
        owning_doctor_id=owning_doctor_id,
        is_open=is_open,
    )
    db_session.add(pair)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


class TestStateMachine:
    async def test_every_legal_transition_succeeds(
        self, db_session, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        proposal = await _make_bare_proposal(db_session, auth_client, second_auth_client)
        proposal = await transition_proposal_status(
            db_session, proposal, ExchangeProposalStatus.ACCEPTED
        )
        assert proposal.status == ExchangeProposalStatus.ACCEPTED

        proposal = await transition_proposal_status(
            db_session, proposal, ExchangeProposalStatus.COMPLETED
        )
        assert proposal.status == ExchangeProposalStatus.COMPLETED

    @pytest.mark.parametrize(
        "current,requested",
        [
            (ExchangeProposalStatus.DECLINED, ExchangeProposalStatus.PROPOSED),
            (ExchangeProposalStatus.EXPIRED, ExchangeProposalStatus.ACCEPTED),
            (ExchangeProposalStatus.CANCELLED, ExchangeProposalStatus.PROPOSED),
            (ExchangeProposalStatus.COMPLETED, ExchangeProposalStatus.CANCELLED),
            (ExchangeProposalStatus.PROPOSED, ExchangeProposalStatus.COMPLETED),
        ],
    )
    async def test_illegal_transitions_raise_and_leave_status_unchanged(
        self,
        db_session,
        auth_client: AsyncClient,
        second_auth_client: AsyncClient,
        current: ExchangeProposalStatus,
        requested: ExchangeProposalStatus,
    ):
        proposal = await _make_bare_proposal(
            db_session, auth_client, second_auth_client, status=current
        )

        with pytest.raises(IllegalExchangeProposalTransition):
            await transition_proposal_status(db_session, proposal, requested)

        result = await db_session.execute(
            select(ExchangeProposal).where(ExchangeProposal.id == proposal.id)
        )
        assert result.scalar_one().status == current

    async def test_is_open_mirrors_status_through_a_transition(
        self, db_session, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        proposal = await _make_bare_proposal(db_session, auth_client, second_auth_client)

        await transition_proposal_status(db_session, proposal, ExchangeProposalStatus.DECLINED)

        result = await db_session.execute(
            select(ExchangeProposalPair).where(ExchangeProposalPair.proposal_id == proposal.id)
        )
        pairs = result.scalars().all()
        assert all(pair.is_open is False for pair in pairs)


class TestOverlapInvariantAtDatabaseLevel:
    async def test_partial_unique_index_rejects_a_second_open_proposal_for_the_same_donor(
        self, db_session, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        """K13: the overlap invariant must fail at the database level, not
        just the application check -- this test bypasses create_proposal's
        pre-check entirely and inserts two open ExchangeProposalPair rows
        for the same donor directly, proving the partial unique index
        alone is what stops it."""
        patient = await create_patient(auth_client, blood_type="A")
        donor = await create_donor(auth_client, blood_type="B", intended_recipient_id=patient["id"])
        owning_doctor_id = await _doctor_id(auth_client)
        proposer_id = await _doctor_id(second_auth_client)

        def _new_proposal() -> ExchangeProposal:
            return ExchangeProposal(
                created_by_doctor_id=proposer_id,
                policy="max_transplants",
                weight=1.0,
                cycle_snapshot={"nodes": [], "edges": []},
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )

        first_proposal = _new_proposal()
        db_session.add(first_proposal)
        await db_session.flush()
        db_session.add(
            ExchangeProposalPair(
                proposal_id=first_proposal.id,
                donor_id=uuid.UUID(donor["id"]),
                patient_id=uuid.UUID(patient["id"]),
                owning_doctor_id=owning_doctor_id,
                is_open=True,
            )
        )
        await db_session.commit()

        second_proposal = _new_proposal()
        db_session.add(second_proposal)
        await db_session.flush()
        db_session.add(
            ExchangeProposalPair(
                proposal_id=second_proposal.id,
                donor_id=uuid.UUID(donor["id"]),
                patient_id=uuid.UUID(patient["id"]),
                owning_doctor_id=owning_doctor_id,
                is_open=True,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestExpiry:
    async def test_lazy_expiry_releases_a_reserved_donor_and_marks_expired(
        self, db_session, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        proposal = await _make_bare_proposal(
            db_session,
            auth_client,
            second_auth_client,
            status=ExchangeProposalStatus.PROPOSED,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        result = await db_session.execute(
            select(ExchangeProposalPair).where(ExchangeProposalPair.proposal_id == proposal.id)
        )
        pair = result.scalars().one()
        donor_result = await db_session.execute(select(Donor).where(Donor.id == pair.donor_id))
        donor = donor_result.scalar_one()
        donor.status = DonorStatus.RESERVED
        await db_session.commit()

        proposal = await expire_if_due(db_session, proposal)

        assert proposal.status == ExchangeProposalStatus.EXPIRED
        await db_session.refresh(donor)
        assert donor.status == DonorStatus.AVAILABLE
        await db_session.refresh(pair)
        assert pair.is_open is False

    async def test_not_yet_due_is_left_alone(
        self, db_session, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        proposal = await _make_bare_proposal(
            db_session,
            auth_client,
            second_auth_client,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

        proposal = await expire_if_due(db_session, proposal)

        assert proposal.status == ExchangeProposalStatus.PROPOSED

    async def test_startup_sweep_expires_every_due_proposal(
        self, db_session, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        due = await _make_bare_proposal(
            db_session,
            auth_client,
            second_auth_client,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        not_due = await _make_bare_proposal(
            db_session,
            auth_client,
            second_auth_client,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

        expired_count = await sweep_expired_proposals(db_session)

        assert expired_count == 1
        result = await db_session.execute(
            select(ExchangeProposal).where(ExchangeProposal.id == due.id)
        )
        assert result.scalar_one().status == ExchangeProposalStatus.EXPIRED
        result = await db_session.execute(
            select(ExchangeProposal).where(ExchangeProposal.id == not_due.id)
        )
        assert result.scalar_one().status == ExchangeProposalStatus.PROPOSED


class TestSnapshotImmutability:
    async def test_cycle_snapshot_keeps_the_hla_frequency_table_version_in_force_at_proposal_time(
        self, monkeypatch, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        patient_a = await create_patient(auth_client, blood_type="A")
        patient_b = await create_patient(second_auth_client, blood_type="B")
        donor_a = await create_donor(
            auth_client, blood_type="B", intended_recipient_id=patient_a["id"]
        )
        donor_b = await create_donor(
            second_auth_client, blood_type="A", intended_recipient_id=patient_b["id"]
        )
        for client, patient_id in (
            (auth_client, patient_a["id"]), (second_auth_client, patient_b["id"]),
        ):
            assert (
                await client.put(f"/patients/{patient_id}/hla-typings", json=MATCHING_TYPING)
            ).status_code == 204
        for client, donor_id in ((auth_client, donor_a["id"]), (second_auth_client, donor_b["id"])):
            assert (
                await client.put(f"/donors/{donor_id}/hla-typings", json=MATCHING_TYPING)
            ).status_code == 204

        match_response = await auth_client.get(
            "/exchange/match", params={"policy": "max_transplants"}
        )
        cycle = match_response.json()["selected_cycles"][0]

        create_response = await auth_client.post(
            "/exchange/proposals",
            json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]},
        )
        assert create_response.status_code == 201, create_response.text
        proposal_id = create_response.json()["id"]
        original_version = create_response.json()["cycle_snapshot"]["hla_frequency_table_version"]

        # Patched where exchange_proposal_service actually bound the name at
        # import time (a `from X import Y` copies the reference -- patching
        # X.Y afterward wouldn't touch it) -- proves the stored snapshot
        # isn't re-derived from the live constant on read, not just that a
        # module-level import didn't move.
        monkeypatch.setattr(
            "app.services.exchange_proposal_service.HLA_FREQUENCY_TABLE_VERSION",
            "some-future-table-v99",
        )

        read_response = await auth_client.get(f"/exchange/proposals/{proposal_id}")
        assert (
            read_response.json()["cycle_snapshot"]["hla_frequency_table_version"]
            == original_version
        )
        assert original_version != "some-future-table-v99"

# app/tests/integration/test_exchange_proposals_api.py
"""
HTTP-level coverage for POST/GET /exchange/proposals and its sub-routes.
Seeds a real two-way swap (same fixture shape as test_exchange_api.py) as
the common starting point for most tests here.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app as fastapi_app
from app.models.audit_log import AuditLog
from app.models.exchange_proposal import ExchangeProposal
from app.tests.conftest import _unique_email, create_donor, create_patient

MATCHING_TYPING = [
    {"locus": "A", "allele_1": "01", "allele_2": "02"},
    {"locus": "B", "allele_1": "07", "allele_2": "08"},
    {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
]


async def _make_third_client() -> AsyncClient:
    """A third, independent doctor -- for authorization tests where neither
    `auth_client` nor `second_auth_client` should be allowed to act (they
    both own a pair in the seeded swap)."""
    transport = ASGITransport(app=fastapi_app)
    ac = AsyncClient(transport=transport, base_url="http://test")
    payload = {
        "hospital_name": "Third Test Hospital",
        "email": _unique_email(),
        "password": "correct-horse-battery-staple",
        "full_name": "Dr. Third Doctor",
    }
    assert (await ac.post("/auth/register", json=payload)).status_code == 201
    login = await ac.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 200
    ac.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return ac


async def _seed_two_way_swap(auth_client: AsyncClient, second_auth_client: AsyncClient) -> dict:
    patient_a = await create_patient(auth_client, blood_type="A")
    patient_b = await create_patient(second_auth_client, blood_type="B")
    donor_a = await create_donor(auth_client, blood_type="B", intended_recipient_id=patient_a["id"])
    donor_b = await create_donor(
        second_auth_client, blood_type="A", intended_recipient_id=patient_b["id"]
    )
    for client, patient_id in ((auth_client, patient_a["id"]), (second_auth_client, patient_b["id"])):
        assert (
            await client.put(f"/patients/{patient_id}/hla-typings", json=MATCHING_TYPING)
        ).status_code == 204
    for client, donor_id in ((auth_client, donor_a["id"]), (second_auth_client, donor_b["id"])):
        assert (
            await client.put(f"/donors/{donor_id}/hla-typings", json=MATCHING_TYPING)
        ).status_code == 204
    return {"patient_a": patient_a, "patient_b": patient_b, "donor_a": donor_a, "donor_b": donor_b}


async def _seeded_cycle(auth_client: AsyncClient, policy: str = "max_transplants") -> dict:
    response = await auth_client.get("/exchange/match", params={"policy": policy})
    assert response.status_code == 200, response.text
    cycles = response.json()["selected_cycles"]
    assert len(cycles) == 1, "expected the seeded two-way swap to produce exactly one cycle"
    return cycles[0]


class TestCreateProposal:
    async def test_creates_a_proposal_from_a_real_selected_cycle(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient, db_session
    ):
        seeded = await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)

        response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "proposed"
        assert body["policy"] == "max_transplants"
        assert {pair["donor_id"] for pair in body["pairs"]} == set(cycle["pair_ids"])
        assert all(pair["decision"] == "pending" for pair in body["pairs"])
        assert len(body["cycle_snapshot"]["nodes"]) == 2
        assert len(body["cycle_snapshot"]["edges"]) == 2

        # Donors are NOT reserved at proposal time (K4) -- only on full
        # acceptance. Donor CRUD reads are owner-scoped, so each side reads
        # its own donor.
        assert (await auth_client.get(f"/donors/{seeded['donor_a']['id']}")).json()["status"] == "available"
        assert (
            await second_auth_client.get(f"/donors/{seeded['donor_b']['id']}")
        ).json()["status"] == "available"

        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "proposed_exchange_cycle")
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].details["proposal_id"] == body["id"]

    async def test_rejects_a_cycle_not_in_the_current_selected_set(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)

        response = await auth_client.post(
            "/exchange/proposals",
            json={"policy": "max_transplants", "pair_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
        )

        assert response.status_code == 400

    async def test_rejects_an_unknown_policy(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)

        response = await auth_client.post(
            "/exchange/proposals", json={"policy": "not_a_real_policy", "pair_ids": []}
        )

        assert response.status_code == 400

    async def test_conflicts_when_a_pair_is_already_in_an_open_proposal(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)

        first = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        assert first.status_code == 201

        second = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )

        assert second.status_code == 409
        assert first.json()["id"] in second.json()["detail"]

    async def test_concurrent_creation_yields_exactly_one_201_and_one_409(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        payload = {"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}

        responses = await asyncio.gather(
            auth_client.post("/exchange/proposals", json=payload),
            auth_client.post("/exchange/proposals", json=payload),
        )

        statuses = sorted(response.status_code for response in responses)
        assert statuses == [201, 409]


class TestListAndGetProposal:
    async def test_get_is_visible_to_a_doctor_who_owns_no_pair_in_it(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        proposal_id = create_response.json()["id"]

        third_client = await _make_third_client()
        try:
            response = await third_client.get(f"/exchange/proposals/{proposal_id}")
            assert response.status_code == 200
        finally:
            await third_client.aclose()

    async def test_get_missing_proposal_404s(self, auth_client: AsyncClient):
        response = await auth_client.get(f"/exchange/proposals/{uuid.uuid4()}")
        assert response.status_code == 404

    async def test_mine_filter_returns_only_proposals_with_a_pending_pair_i_own(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )

        mine_response = await auth_client.get("/exchange/proposals", params={"mine": "true"})
        assert mine_response.status_code == 200
        assert len(mine_response.json()) == 1

        third_client = await _make_third_client()
        try:
            not_mine_response = await third_client.get(
                "/exchange/proposals", params={"mine": "true"}
            )
            assert not_mine_response.json() == []

            unfiltered_response = await third_client.get("/exchange/proposals")
            assert len(unfiltered_response.json()) == 1
        finally:
            await third_client.aclose()


class TestDecisionEndpoint:
    async def test_requires_the_pairs_owning_doctor(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        body = create_response.json()
        proposal_id = body["id"]
        # auth_client owns donor_a's pair -- find second_auth_client's pair.
        auth_client_doctor_id = (await auth_client.get("/auth/me")).json()["id"]
        other_pair = next(
            pair for pair in body["pairs"] if pair["owning_doctor_id"] != auth_client_doctor_id
        )

        wrong_doctor_response = await auth_client.post(
            f"/exchange/proposals/{proposal_id}/pairs/{other_pair['id']}/decision",
            json={"decision": "accepted"},
        )
        assert wrong_doctor_response.status_code == 403

        right_doctor_response = await second_auth_client.post(
            f"/exchange/proposals/{proposal_id}/pairs/{other_pair['id']}/decision",
            json={"decision": "accepted"},
        )
        assert right_doctor_response.status_code == 200

    async def test_full_acceptance_reserves_donors_only_on_the_last_acceptance_and_locks_the_cycle(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient, db_session
    ):
        seeded = await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        body = create_response.json()
        proposal_id = body["id"]
        pair_by_donor_id = {pair["donor_id"]: pair for pair in body["pairs"]}

        first_response = await auth_client.post(
            f"/exchange/proposals/{proposal_id}/pairs/{pair_by_donor_id[seeded['donor_a']['id']]['id']}/decision",
            json={"decision": "accepted"},
        )
        assert first_response.status_code == 200
        assert first_response.json()["status"] == "proposed"  # not locked yet

        donor_a_after_first = await auth_client.get(f"/donors/{seeded['donor_a']['id']}")
        assert donor_a_after_first.json()["status"] == "available"

        second_response = await second_auth_client.post(
            f"/exchange/proposals/{proposal_id}/pairs/{pair_by_donor_id[seeded['donor_b']['id']]['id']}/decision",
            json={"decision": "accepted"},
        )
        assert second_response.status_code == 200
        assert second_response.json()["status"] == "accepted"

        assert (await auth_client.get(f"/donors/{seeded['donor_a']['id']}")).json()["status"] == "reserved"
        assert (
            await second_auth_client.get(f"/donors/{seeded['donor_b']['id']}")
        ).json()["status"] == "reserved"

        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "locked_exchange_cycle")
        )
        assert len(result.scalars().all()) == 1

    async def test_decline_declines_the_whole_proposal_and_never_reserves(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        seeded = await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        body = create_response.json()
        proposal_id = body["id"]
        own_pair = next(
            pair for pair in body["pairs"] if pair["donor_id"] == seeded["donor_a"]["id"]
        )

        response = await auth_client.post(
            f"/exchange/proposals/{proposal_id}/pairs/{own_pair['id']}/decision",
            json={"decision": "declined", "decline_reason": "changed our minds"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "declined"
        assert (await auth_client.get(f"/donors/{seeded['donor_a']['id']}")).json()["status"] == "available"
        assert (
            await second_auth_client.get(f"/donors/{seeded['donor_b']['id']}")
        ).json()["status"] == "available"

    async def test_a_pair_that_already_has_a_decision_cannot_be_decided_again(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        seeded = await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        body = create_response.json()
        own_pair = next(
            pair for pair in body["pairs"] if pair["donor_id"] == seeded["donor_a"]["id"]
        )

        first = await auth_client.post(
            f"/exchange/proposals/{body['id']}/pairs/{own_pair['id']}/decision",
            json={"decision": "declined"},
        )
        assert first.status_code == 200

        second = await auth_client.post(
            f"/exchange/proposals/{body['id']}/pairs/{own_pair['id']}/decision",
            json={"decision": "accepted"},
        )
        assert second.status_code == 409


class TestCancelEndpoint:
    async def test_requires_the_proposer_or_an_admin(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        proposal_id = create_response.json()["id"]

        third_client = await _make_third_client()
        try:
            forbidden_response = await third_client.post(f"/exchange/proposals/{proposal_id}/cancel")
            assert forbidden_response.status_code == 403
        finally:
            await third_client.aclose()

        allowed_response = await auth_client.post(f"/exchange/proposals/{proposal_id}/cancel")
        assert allowed_response.status_code == 200
        assert allowed_response.json()["status"] == "cancelled"

    async def test_cancelling_an_accepted_proposal_releases_reserved_donors(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        seeded = await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        body = create_response.json()
        pair_by_donor_id = {pair["donor_id"]: pair for pair in body["pairs"]}
        await auth_client.post(
            f"/exchange/proposals/{body['id']}/pairs/{pair_by_donor_id[seeded['donor_a']['id']]['id']}/decision",
            json={"decision": "accepted"},
        )
        await second_auth_client.post(
            f"/exchange/proposals/{body['id']}/pairs/{pair_by_donor_id[seeded['donor_b']['id']]['id']}/decision",
            json={"decision": "accepted"},
        )
        assert (await auth_client.get(f"/donors/{seeded['donor_a']['id']}")).json()["status"] == "reserved"
        assert (
            await second_auth_client.get(f"/donors/{seeded['donor_b']['id']}")
        ).json()["status"] == "reserved"

        cancel_response = await auth_client.post(f"/exchange/proposals/{body['id']}/cancel")

        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"
        assert (await auth_client.get(f"/donors/{seeded['donor_a']['id']}")).json()["status"] == "available"
        assert (
            await second_auth_client.get(f"/donors/{seeded['donor_b']['id']}")
        ).json()["status"] == "available"

    async def test_cancelling_an_already_cancelled_proposal_is_idempotent(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        # Re-affirming the current status is a no-op success, not an error
        # -- same "same-status is a pass-through" contract
        # donor_service.update_donor_status uses (see
        # transition_proposal_status's `status != proposal.status` guard).
        await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        proposal_id = create_response.json()["id"]
        assert (await auth_client.post(f"/exchange/proposals/{proposal_id}/cancel")).status_code == 200

        second_cancel = await auth_client.post(f"/exchange/proposals/{proposal_id}/cancel")

        assert second_cancel.status_code == 200
        assert second_cancel.json()["status"] == "cancelled"

    async def test_cancelling_a_declined_proposal_409s(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient
    ):
        # DECLINED -> CANCELLED is a genuinely different, disallowed
        # transition (unlike CANCELLED -> CANCELLED above).
        seeded = await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        body = create_response.json()
        own_pair = next(
            pair for pair in body["pairs"] if pair["donor_id"] == seeded["donor_a"]["id"]
        )
        assert (
            await auth_client.post(
                f"/exchange/proposals/{body['id']}/pairs/{own_pair['id']}/decision",
                json={"decision": "declined"},
            )
        ).status_code == 200

        response = await auth_client.post(f"/exchange/proposals/{body['id']}/cancel")

        assert response.status_code == 409


class TestExpiryOnRead:
    async def test_expired_proposal_releases_pairs_and_frees_the_donor_for_a_new_proposal(
        self, auth_client: AsyncClient, second_auth_client: AsyncClient, db_session
    ):
        await _seed_two_way_swap(auth_client, second_auth_client)
        cycle = await _seeded_cycle(auth_client)
        create_response = await auth_client.post(
            "/exchange/proposals", json={"policy": "max_transplants", "pair_ids": cycle["pair_ids"]}
        )
        proposal_id = create_response.json()["id"]

        # Force the proposal into the past directly -- there's no API to
        # backdate expires_at, this is the "days pass" simulation.
        result = await db_session.execute(
            select(ExchangeProposal).where(ExchangeProposal.id == uuid.UUID(proposal_id))
        )
        proposal = result.scalar_one()
        proposal.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db_session.commit()

        get_response = await auth_client.get(f"/exchange/proposals/{proposal_id}")

        assert get_response.json()["status"] == "expired"

        # The donor is free again -- a new proposal over the same cycle
        # must now succeed (the overlap invariant no longer applies to a
        # closed proposal).
        new_cycle = await _seeded_cycle(auth_client)
        retry_response = await auth_client.post(
            "/exchange/proposals",
            json={"policy": "max_transplants", "pair_ids": new_cycle["pair_ids"]},
        )
        assert retry_response.status_code == 201

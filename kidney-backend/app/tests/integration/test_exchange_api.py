# app/tests/integration/test_exchange_api.py
"""
HTTP-level coverage for GET /exchange/match. Seeds a real, textbook 2-way
paired swap across two doctors (A-recipient/B-donor and B-recipient/
A-donor -- each direct pairing is ABO-incompatible on its own, but swapped
both work) and confirms the endpoint discovers and selects it.
"""
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.tests.conftest import create_donor, create_patient

MATCHING_TYPING = [
    {"locus": "A", "allele_1": "01", "allele_2": "02"},
    {"locus": "B", "allele_1": "07", "allele_2": "08"},
    {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
]


async def _seed_two_way_swap(auth_client: AsyncClient, second_auth_client: AsyncClient) -> dict:
    patient_a = await create_patient(auth_client, blood_type="A")
    patient_b = await create_patient(second_auth_client, blood_type="B")
    donor_a = await create_donor(
        auth_client, blood_type="B", intended_recipient_id=patient_a["id"]
    )
    donor_b = await create_donor(
        second_auth_client, blood_type="A", intended_recipient_id=patient_b["id"]
    )

    patient_pairs = ((auth_client, patient_a["id"]), (second_auth_client, patient_b["id"]))
    for client, patient_id in patient_pairs:
        response = await client.put(f"/patients/{patient_id}/hla-typings", json=MATCHING_TYPING)
        assert response.status_code == 204, response.text

    for client, donor_id in ((auth_client, donor_a["id"]), (second_auth_client, donor_b["id"])):
        response = await client.put(f"/donors/{donor_id}/hla-typings", json=MATCHING_TYPING)
        assert response.status_code == 204, response.text

    return {"patient_a": patient_a, "patient_b": patient_b, "donor_a": donor_a, "donor_b": donor_b}


async def test_match_discovers_and_selects_a_two_way_swap(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    seeded = await _seed_two_way_swap(auth_client, second_auth_client)

    response = await auth_client.get("/exchange/match", params={"policy": "max_transplants"})

    assert response.status_code == 200
    body = response.json()

    node_pair_ids = {node["pair_id"] for node in body["nodes"]}
    assert node_pair_ids == {seeded["donor_a"]["id"], seeded["donor_b"]["id"]}

    edge_pairs = {(edge["from_pair_id"], edge["to_pair_id"]) for edge in body["edges"]}
    assert edge_pairs == {
        (seeded["donor_a"]["id"], seeded["donor_b"]["id"]),
        (seeded["donor_b"]["id"], seeded["donor_a"]["id"]),
    }

    assert len(body["selected_cycles"]) == 1
    cycle = body["selected_cycles"][0]
    assert set(cycle["pair_ids"]) == {seeded["donor_a"]["id"], seeded["donor_b"]["id"]}
    assert cycle["weight"] == 2

    # Both pool pairs are matched, so K7's explanations list -- which only
    # ever covers unmatched pairs -- is empty here.
    assert body["explanations"] == []


async def test_match_discloses_patient_wait_source_per_node(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    # K9: patient_a has a real dialysis_start_date, patient_b doesn't (falls
    # back to created_at) -- both must be disclosed correctly per node, not
    # just internally used to compute a score.
    patient_a = await create_patient(auth_client, blood_type="A", dialysis_start_date="2020-01-01")
    patient_b = await create_patient(second_auth_client, blood_type="B")
    donor_a = await create_donor(auth_client, blood_type="B", intended_recipient_id=patient_a["id"])
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

    response = await auth_client.get("/exchange/match")
    assert response.status_code == 200
    nodes_by_patient_id = {node["patient_id"]: node for node in response.json()["nodes"]}

    assert nodes_by_patient_id[patient_a["id"]]["patient_wait_source"] == "dialysis_start_date"
    assert nodes_by_patient_id[patient_b["id"]]["patient_wait_source"] == "created_at_fallback"


async def test_hard_to_match_endpoint_reports_a_structurally_isolated_pair(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    seeded = await _seed_two_way_swap(auth_client, second_auth_client)

    # patient_c(O)/donor_c(AB): O can only receive an O donor, AB can only
    # give to an AB recipient -- incompatible with itself (admits it to the
    # pool) AND with both existing pairs (donor_a is B, donor_b is A;
    # patient_a is A, patient_b is B) -- zero edges in either direction.
    patient_c = await create_patient(auth_client, blood_type="O", full_name="Isolated Patient")
    donor_c = await create_donor(
        auth_client, blood_type="AB", full_name="Isolated Donor", intended_recipient_id=patient_c["id"]
    )
    assert (
        await auth_client.put(f"/patients/{patient_c['id']}/hla-typings", json=MATCHING_TYPING)
    ).status_code == 204
    assert (
        await auth_client.put(f"/donors/{donor_c['id']}/hla-typings", json=MATCHING_TYPING)
    ).status_code == 204

    response = await auth_client.get("/exchange/hard-to-match")
    assert response.status_code == 200
    body = response.json()

    hard_to_match_pair_ids = {pair["node"]["pair_id"] for pair in body["pairs"]}
    assert donor_c["id"] in hard_to_match_pair_ids
    # The matched swap pair never appears on the hard-to-match worklist.
    assert seeded["donor_a"]["id"] not in hard_to_match_pair_ids
    assert seeded["donor_b"]["id"] not in hard_to_match_pair_ids

    isolated = next(pair for pair in body["pairs"] if pair["node"]["pair_id"] == donor_c["id"])
    assert isolated["verdict"] == "no_donor_out"
    assert isolated["candidate_cycles"] == 0


async def test_match_excludes_a_directly_compatible_pair(auth_client: AsyncClient):
    # AB accepts any blood type and matching A/B/DRB1 typing keeps the
    # mismatch gate from worst-casing this into an incompatible pair (see
    # hla_missing_typing_zero_mismatch_bug fix) -- a genuinely direct-
    # compatible pairing that shouldn't need an exchange at all.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O", intended_recipient_id=patient["id"])
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=MATCHING_TYPING)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=MATCHING_TYPING)

    response = await auth_client.get("/exchange/match")

    assert response.status_code == 200
    assert response.json()["nodes"] == []


async def test_match_excludes_an_untyped_pair(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    # Review #2 bug 11: a donor with no HLA typing at all worst-cases to
    # 6/6 mismatches (calculate_mismatch_result's missing-locus handling),
    # which makes it `is_halted=True` and therefore "not directly
    # compatible" -- exactly the shape of an exchange candidate, except
    # the underlying reason is missing data, not a real mismatch. Such a
    # pair used to be silently admitted to the pool on guessed data.
    patient_a = await create_patient(auth_client, blood_type="A")
    patient_b = await create_patient(second_auth_client, blood_type="B")
    donor_a = await create_donor(
        auth_client, blood_type="B", intended_recipient_id=patient_a["id"]
    )
    donor_b = await create_donor(
        second_auth_client, blood_type="A", intended_recipient_id=patient_b["id"]
    )

    for client, patient_id in ((auth_client, patient_a["id"]), (second_auth_client, patient_b["id"])):
        response = await client.put(f"/patients/{patient_id}/hla-typings", json=MATCHING_TYPING)
        assert response.status_code == 204, response.text

    # donor_a is left with no HLA typing at all -- donor_b is fully typed.
    response = await second_auth_client.put(
        f"/donors/{donor_b['id']}/hla-typings", json=MATCHING_TYPING
    )
    assert response.status_code == 204, response.text

    response = await auth_client.get("/exchange/match", params={"policy": "max_transplants"})

    assert response.status_code == 200
    node_pair_ids = {node["pair_id"] for node in response.json()["nodes"]}
    assert donor_a["id"] not in node_pair_ids
    assert donor_b["id"] in node_pair_ids


async def test_match_rejects_an_unknown_policy(auth_client: AsyncClient):
    response = await auth_client.get("/exchange/match", params={"policy": "not_a_real_policy"})

    assert response.status_code == 400


async def test_compare_reports_a_cycle_every_policy_agrees_on(
    auth_client: AsyncClient, second_auth_client: AsyncClient, db_session
):
    seeded = await _seed_two_way_swap(auth_client, second_auth_client)

    response = await auth_client.get("/exchange/match/compare")

    assert response.status_code == 200
    body = response.json()

    assert set(body["policies"]) == {
        "max_transplants", "max_quality", "equity_weighted", "max_lkdpi_quality",
    }
    assert len(body["cycles"]) == 1
    cycle = body["cycles"][0]
    assert set(cycle["pair_ids"]) == {seeded["donor_a"]["id"], seeded["donor_b"]["id"]}
    # The only candidate cycle in a 2-pair pool -- every policy with a
    # positive weight to assign has nothing else to choose, so it selects
    # this cycle. max_lkdpi_quality is deliberately excluded from this
    # assertion: these fixture donors/patients don't carry LKDPI inputs
    # (weight, sex, biological relationship), so that policy scores this
    # cycle 0 and ties with the empty selection -- a legitimate, policy-
    # specific tie (see weight_max_lkdpi_quality's docstring), not something
    # this test should pin to one arbitrary side of.
    assert {"max_transplants", "max_quality", "equity_weighted"} <= set(cycle["selected_by"])

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "compared_exchange_policies")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].details["pool_size"] == 2


async def test_match_writes_audit_log_entry(
    auth_client: AsyncClient, second_auth_client: AsyncClient, db_session
):
    await _seed_two_way_swap(auth_client, second_auth_client)

    response = await auth_client.get("/exchange/match", params={"policy": "max_transplants"})
    assert response.status_code == 200

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ran_exchange_matching")
    )
    entries = result.scalars().all()

    assert len(entries) == 1
    assert entries[0].doctor_id is not None
    assert entries[0].details["policy"] == "max_transplants"
    assert entries[0].details["pool_size"] == 2
    assert entries[0].details["pairs_transplanted"] == 2

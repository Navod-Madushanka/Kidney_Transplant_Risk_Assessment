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


async def test_match_rejects_an_unknown_policy(auth_client: AsyncClient):
    response = await auth_client.get("/exchange/match", params={"policy": "not_a_real_policy"})

    assert response.status_code == 400


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

# app/tests/integration/test_donors.py
from httpx import AsyncClient

from app.tests.conftest import create_donor, make_donor_payload


async def test_create_donor(auth_client: AsyncClient):
    response = await auth_client.post("/donors", json=make_donor_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Bob Donor"
    assert body["blood_type"] == "O"
    assert "id" in body


async def test_create_donor_requires_auth(client: AsyncClient):
    response = await client.post("/donors", json=make_donor_payload())

    assert response.status_code in (401, 403)


async def test_list_donors_returns_only_this_doctors_donors(auth_client: AsyncClient):
    await create_donor(auth_client)
    await create_donor(auth_client, full_name="Second Donor")

    response = await auth_client.get("/donors")

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_get_donor_by_id(auth_client: AsyncClient):
    created = await create_donor(auth_client)

    response = await auth_client.get(f"/donors/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_nonexistent_donor_is_404(auth_client: AsyncClient):
    response = await auth_client.get("/donors/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_replace_and_get_donor_hla_typings(auth_client: AsyncClient):
    donor = await create_donor(auth_client)
    entries = [{"locus": "B", "allele_1": "40", "allele_2": "40"}]

    put_response = await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=entries)
    get_response = await auth_client.get(f"/donors/{donor['id']}/hla-typings")

    assert put_response.status_code == 204
    assert get_response.status_code == 200
    assert len(get_response.json()) == 1
    assert get_response.json()[0]["locus"] == "B"


async def test_replace_donor_hla_typings_for_nonexistent_donor_is_404(auth_client: AsyncClient):
    entries = [{"locus": "B", "allele_1": "40", "allele_2": "40"}]

    response = await auth_client.put(
        "/donors/00000000-0000-0000-0000-000000000000/hla-typings", json=entries
    )

    assert response.status_code == 404

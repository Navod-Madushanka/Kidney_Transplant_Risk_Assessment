# app/tests/integration/test_auth.py
from httpx import AsyncClient


async def test_register_creates_doctor_and_returns_token(client: AsyncClient, register_payload):
    response = await client.post("/auth/register", json=register_payload)

    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_register_duplicate_email_is_rejected(client: AsyncClient, register_payload):
    first = await client.post("/auth/register", json=register_payload)
    assert first.status_code == 201

    second = await client.post("/auth/register", json=register_payload)

    assert second.status_code == 400


async def test_register_rejects_missing_fields(client: AsyncClient):
    response = await client.post("/auth/register", json={"email": "incomplete@example.com"})

    assert response.status_code == 422


async def test_login_with_correct_credentials_returns_token(
    client: AsyncClient, registered_doctor
):
    response = await client.post(
        "/auth/login",
        json={"email": registered_doctor["email"], "password": registered_doctor["password"]},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_login_with_wrong_password_is_unauthorized(
    client: AsyncClient, registered_doctor
):
    response = await client.post(
        "/auth/login",
        json={"email": registered_doctor["email"], "password": "definitely-not-it"},
    )

    assert response.status_code == 401


async def test_login_with_unknown_email_is_unauthorized(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "whatever123"},
    )

    assert response.status_code == 401


async def test_token_from_login_authenticates_subsequent_requests(
    client: AsyncClient, registered_doctor
):
    login = await client.post(
        "/auth/login",
        json={"email": registered_doctor["email"], "password": registered_doctor["password"]},
    )
    token = login.json()["access_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == registered_doctor["email"]


async def test_protected_route_without_token_is_unauthorized(client: AsyncClient):
    response = await client.get("/auth/me")

    assert response.status_code in (401, 403)

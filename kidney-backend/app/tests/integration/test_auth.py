# app/tests/integration/test_auth.py
from httpx import AsyncClient


async def test_register_endpoint_does_not_exist(client: AsyncClient):
    # Closed 2026-08-21: self-service signup is a real exposure risk (any
    # network-reachable client could create a doctor account), so there is
    # no route to hit at all -- see app/api/auth.py and
    # app/scripts/promote_admin.py for how accounts are provisioned now.
    response = await client.post(
        "/auth/register",
        json={
            "hospital_name": "Anyone's Hospital",
            "email": "anyone@example.com",
            "password": "whatever123",
            "full_name": "Anyone",
        },
    )

    assert response.status_code == 404


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

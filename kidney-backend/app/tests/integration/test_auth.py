# app/tests/integration/test_auth.py
from httpx import AsyncClient

from app.services.login_throttle_service import (
    MAX_ACCOUNT_FAILURES_BEFORE_LOCK,
    MAX_IP_FAILURES_BEFORE_LOCK,
)


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


async def test_repeated_failed_logins_lock_the_account(
    client: AsyncClient, registered_doctor
):
    # MAX_ACCOUNT_FAILURES_BEFORE_LOCK - 1 wrong attempts still just 401 --
    # a doctor fat-fingering their password a couple of times shouldn't be
    # locked out on the next correct attempt.
    for _ in range(MAX_ACCOUNT_FAILURES_BEFORE_LOCK - 1):
        response = await client.post(
            "/auth/login",
            json={"email": registered_doctor["email"], "password": "wrong-password"},
        )
        assert response.status_code == 401

    # The failure that crosses the threshold locks the account.
    response = await client.post(
        "/auth/login",
        json={"email": registered_doctor["email"], "password": "wrong-password"},
    )
    assert response.status_code == 401

    locked_response = await client.post(
        "/auth/login",
        json={"email": registered_doctor["email"], "password": "wrong-password"},
    )
    assert locked_response.status_code == 429
    assert "Retry-After" in locked_response.headers

    # The lockout blocks even the *correct* password until it expires --
    # otherwise an attacker who eventually guesses right sails straight
    # through regardless of how many attempts it took.
    correct_password_response = await client.post(
        "/auth/login",
        json={"email": registered_doctor["email"], "password": registered_doctor["password"]},
    )
    assert correct_password_response.status_code == 429


async def test_ip_lockout_catches_spraying_across_many_unknown_accounts(client: AsyncClient):
    # No single email here ever reaches MAX_ACCOUNT_FAILURES_BEFORE_LOCK --
    # each one is only ever tried once. Only the per-IP counter (all of
    # these share one IP under ASGITransport) can catch this pattern. The
    # request that crosses the threshold still gets a plain 401 itself (the
    # lock takes effect for the *next* request, not retroactively for the
    # one that triggered it -- see login_throttle_service's record_failure),
    # so this needs MAX_IP_FAILURES_BEFORE_LOCK failing requests, then one
    # more to observe the lock.
    for i in range(MAX_IP_FAILURES_BEFORE_LOCK):
        response = await client.post(
            "/auth/login",
            json={"email": f"nobody-{i}@example.com", "password": "whatever123"},
        )
        assert response.status_code == 401

    locked_response = await client.post(
        "/auth/login",
        json={"email": "one-more-unknown@example.com", "password": "whatever123"},
    )
    assert locked_response.status_code == 429

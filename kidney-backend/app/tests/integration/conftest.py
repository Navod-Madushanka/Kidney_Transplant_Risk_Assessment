# app/tests/integration/conftest.py
"""
Database-backed fixtures for the integration suite only.

These tests exercise the real FastAPI app end-to-end (HTTP layer down
through the DB), so they need a real Postgres database — SQLite won't do,
since app/services/dashboard_service.py relies on Postgres-specific
`DISTINCT ON` syntax. Point TEST_DATABASE_URL at a scratch database before
running (see kidney-backend/README.md for the default local setup); never
point it at a database you care about, since the schema is dropped and
recreated around the whole test session and every table is truncated
between tests.

Everything here is scoped to `app/tests/integration` by pytest's normal
conftest cascade — `app/tests/unit` never sees or needs any of this, which
is what lets it run with no Postgres reachable. Plain (non-DB) helpers
shared by both suites live in `app/tests/conftest.py`.
"""
import os
import shutil
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — registers every mapped model on Base.metadata
from app.db.base import Base
from app.main import app as fastapi_app
from app.tests.conftest import register_test_doctor

_test_engine = create_async_engine(os.environ["DATABASE_URL"], future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

# Set by app/tests/conftest.py before any `app.*` import (Settings reads
# them at import time); guaranteed present by the time this module loads.
_REPORT_FILES_TEST_DIR = os.environ["REPORT_FILES_STORAGE_DIR"]
_OCR_SPOOL_TEST_DIR = os.environ["OCR_SPOOL_DIR"]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _test_schema() -> AsyncIterator[None]:
    """Creates every table once for the whole test session, drops them all
    afterward. Session-scoped so we're not paying migration/DDL cost per
    test — row-level isolation between tests is handled by `_clean_tables`."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _report_files_scratch_dir_cleanup() -> Iterator[None]:
    """Removes the scratch uploads directory (see REPORT_FILES_STORAGE_DIR
    above) at the end of the test session — DB row cleanup is handled by
    `_clean_tables`, but the files that back those rows live outside the DB
    and need their own cleanup so repeated test runs don't accumulate them.
    """
    yield
    shutil.rmtree(_REPORT_FILES_TEST_DIR, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _ocr_spool_scratch_dir_cleanup() -> Iterator[None]:
    """Same reasoning as _report_files_scratch_dir_cleanup above, for the
    OCR upload spool directory (see OCR_SPOOL_DIR above and
    app/services/ocr_spool_service.py)."""
    yield
    shutil.rmtree(_OCR_SPOOL_TEST_DIR, ignore_errors=True)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Runs after every integration test: truncates every table so no test
    ever sees data left behind by a previous one. TRUNCATE ... CASCADE
    sidesteps having to know FK dependency order ourselves."""
    yield
    async with _test_engine.begin() as conn:
        table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        if table_names:
            await conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Unauthenticated httpx client wired directly to the FastAPI app via
    ASGITransport — no real network socket, so no server process to manage."""
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Direct DB access for assertions the HTTP API has no endpoint for
    (e.g. tampering with a row to test verify_audit_chain), plus test-only
    operator actions like promoting a doctor to admin (see
    test_audit_logs.py's _promote_to_admin -- there's no self-service
    promotion endpoint by design)."""
    async with _TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def registered_doctor(db_session: AsyncSession) -> dict:
    """A doctor provisioned directly (see register_test_doctor) and its
    plaintext credentials, so tests have someone to log in as."""
    return await register_test_doctor(db_session)


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, registered_doctor: dict) -> AsyncClient:
    """An httpx client for a freshly-registered doctor, already carrying a
    valid Authorization header — the starting point for most integration
    tests, which care about patient/donor/compatibility behavior rather
    than auth itself."""
    response = await client.post(
        "/auth/login",
        json={"email": registered_doctor["email"], "password": registered_doctor["password"]},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest_asyncio.fixture
async def second_auth_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A second, independently-provisioned-and-logged-in doctor at a
    different hospital, on its own AsyncClient — for cross-hospital donor
    search/matching tests that need two distinct accounts talking to the
    same app/DB. Separate from `auth_client` (which wraps the shared
    `client` fixture) so both doctors' sessions can be used side by side in
    the same test.
    """
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        credentials = await register_test_doctor(
            db_session, hospital_name="Second Test Hospital", full_name="Dr. Second Doctor"
        )

        login_response = await ac.post(
            "/auth/login",
            json={"email": credentials["email"], "password": credentials["password"]},
        )
        assert login_response.status_code == 200, login_response.text

        ac.headers["Authorization"] = f"Bearer {login_response.json()['access_token']}"
        yield ac

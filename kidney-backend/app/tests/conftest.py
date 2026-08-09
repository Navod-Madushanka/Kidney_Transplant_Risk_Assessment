# app/tests/conftest.py
"""
Shared pytest fixtures for both the unit and integration suites.

Integration tests exercise the real FastAPI app end-to-end (HTTP layer down
through the DB), so they need a real Postgres database — SQLite won't do,
since app/services/dashboard_service.py relies on Postgres-specific
`DISTINCT ON` syntax. Point TEST_DATABASE_URL at a scratch database before
running (see kidney-backend/README.md for the default local setup); never
point it at a database you care about, since the schema is dropped and
recreated around the whole test session and every table is truncated
between tests.
"""
import os

# Must happen before any `app.*` import: app.core.config.Settings reads
# these from the environment at import time (app.db.session builds its
# engine from settings.database_url as soon as it's imported), and
# get_settings() is @lru_cache'd, so once something else imports it first
# with the wrong values, we're stuck with them for the rest of the process.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:devpass@localhost:5432/kidney_transplant_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ.setdefault("OCR_SERVICE_API_KEY", "test-ocr-service-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import tempfile  # noqa: E402

_REPORT_FILES_TEST_DIR = os.path.join(tempfile.gettempdir(), "kidney_test_uploads")
os.environ.setdefault("REPORT_FILES_STORAGE_DIR", _REPORT_FILES_TEST_DIR)
# Small on purpose so the oversized-file test doesn't need to allocate
# a real 20MB+ payload.
os.environ.setdefault("REPORT_FILES_MAX_SIZE_MB", "1")

import shutil  # noqa: E402
import uuid  # noqa: E402
from typing import AsyncIterator, Iterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models  # noqa: E402,F401 — registers every mapped model on Base.metadata
from app.db.base import Base  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

_test_engine = create_async_engine(os.environ["DATABASE_URL"], future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


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


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Runs after every test (unit and integration alike, though only
    integration tests populate any rows): truncates every table so no test
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


def _unique_email() -> str:
    return f"doctor-{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture
def register_payload() -> dict:
    """A fresh, valid /auth/register payload. Call _unique_email() again
    (or override the 'email' key) if a test needs more than one doctor."""
    return {
        "hospital_name": "Test General Hospital",
        "email": _unique_email(),
        "password": "correct-horse-battery-staple",
        "full_name": "Dr. Test Doctor",
    }


@pytest_asyncio.fixture
async def registered_doctor(client: AsyncClient, register_payload: dict) -> dict:
    """Registers a doctor via the real /auth/register endpoint and returns
    the payload used (so tests have the email/password to log in with)."""
    response = await client.post("/auth/register", json=register_payload)
    assert response.status_code == 201, response.text
    return register_payload


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
async def second_auth_client() -> AsyncIterator[AsyncClient]:
    """A second, independently-registered-and-logged-in doctor at a
    different hospital, on its own AsyncClient — for cross-hospital donor
    search/matching tests that need two distinct accounts talking to the
    same app/DB. Separate from `auth_client` (which wraps the shared
    `client` fixture) so both doctors' sessions can be used side by side in
    the same test.
    """
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "hospital_name": "Second Test Hospital",
            "email": _unique_email(),
            "password": "correct-horse-battery-staple",
            "full_name": "Dr. Second Doctor",
        }
        register_response = await ac.post("/auth/register", json=payload)
        assert register_response.status_code == 201, register_response.text

        login_response = await ac.post(
            "/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert login_response.status_code == 200, login_response.text

        ac.headers["Authorization"] = f"Bearer {login_response.json()['access_token']}"
        yield ac


def make_patient_payload(**overrides) -> dict:
    payload = {
        "full_name": "Alice Patient",
        "date_of_birth": "1985-06-15",
        "blood_type": "AB",
        "rh_factor": "+",
    }
    payload.update(overrides)
    return payload


def make_donor_payload(**overrides) -> dict:
    payload = {
        "full_name": "Bob Donor",
        "date_of_birth": "1990-02-20",
        "blood_type": "O",
        "rh_factor": "+",
    }
    payload.update(overrides)
    return payload


# The exact patient/donor HLA typing pair from the project's worked lab
# example (see app/tests/unit/test_hla_scoring_service.py) — known-good
# ground truth: total_score == 6.5, which lands in "High-Moderate Risk"
# (5.25-7.0, app/reference_data/risk_tiers.py). Reused here so integration
# tests that need a "completed" pipeline run don't have to re-derive a
# valid full 9-locus typing pair from scratch.
COMPATIBLE_PATIENT_HLA = [
    {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
    {"locus": "B", "allele_1": "07", "allele_2": "58"},
    {"locus": "DQB1", "allele_1": "02", "allele_2": "03"},
    {"locus": "C", "allele_1": "03", "allele_2": "15"},
    {"locus": "A", "allele_1": "29", "allele_2": "33"},
    {"locus": "DRB3,4,5", "allele_1": "DRB3*02", "allele_2": "DRB4*01"},
    {"locus": "DQA1", "allele_1": "03", "allele_2": "05"},
    {"locus": "DPA1", "allele_1": "01", "allele_2": "01"},
    {"locus": "DPB1", "allele_1": "04", "allele_2": "04"},
]

COMPATIBLE_DONOR_HLA = [
    {"locus": "DRB1", "allele_1": "13", "allele_2": "14"},
    {"locus": "B", "allele_1": "40", "allele_2": "40"},
    {"locus": "DQB1", "allele_1": "05", "allele_2": "06"},
    {"locus": "C", "allele_1": "12", "allele_2": "15"},
    {"locus": "A", "allele_1": "33", "allele_2": "33"},
    {"locus": "DRB3,4,5", "allele_1": "DRB3*01", "allele_2": "DRB3*02"},
    {"locus": "DQA1", "allele_1": "01", "allele_2": "01"},
    {"locus": "DPA1", "allele_1": "02", "allele_2": "02"},
    {"locus": "DPB1", "allele_1": "04", "allele_2": "13"},
]


async def create_patient(client: AsyncClient, **overrides) -> dict:
    response = await client.post("/patients", json=make_patient_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def create_donor(client: AsyncClient, **overrides) -> dict:
    response = await client.post("/donors", json=make_donor_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()

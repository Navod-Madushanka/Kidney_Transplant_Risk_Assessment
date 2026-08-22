# app/tests/conftest.py
"""
Shared fixtures and helpers for both the unit and integration suites.

Nothing in this file talks to a database — it only sets env vars (Settings
reads them at import time, see below) and defines plain helper
functions/fixtures that operate on a `client`/`db_session` passed in by the
caller. That's what lets `pytest app/tests/unit` run standalone with no
Postgres reachable.

The database-backed fixtures (`client`, `db_session`, schema create/drop,
per-test truncation, `auth_client`, ...) live in
`app/tests/integration/conftest.py` — see that file's docstring for the
Postgres setup they need. pytest cascades conftest fixtures downward, so
those stay invisible to (and unneeded by) `app/tests/unit`.
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

_OCR_SPOOL_TEST_DIR = os.path.join(tempfile.gettempdir(), "kidney_test_ocr_spool")
os.environ.setdefault("OCR_SPOOL_DIR", _OCR_SPOOL_TEST_DIR)
# Small on purpose, same reasoning as REPORT_FILES_MAX_SIZE_MB above --
# lets the oversized-upload test use a small payload instead of a real
# 15MB+ one.
os.environ.setdefault("OCR_UPLOAD_MAX_SIZE_MB", "1")

import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.services.doctor_service import create_doctor  # noqa: E402
from app.services.hospital_service import get_or_create_hospital  # noqa: E402
from app.services.login_throttle_service import reset_all as reset_login_throttle  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_login_throttle() -> None:
    """Login throttling (app/services/login_throttle_service.py) is
    module-level, in-process state — without this, a test that deliberately
    drives an account/IP into lockout (see test_auth.py) would leave every
    later test in the same session sharing that same locked-out state,
    since the whole suite runs in one process. Harmless (and a no-op in
    effect) for unit tests, which never touch it."""
    reset_login_throttle()


def _unique_email() -> str:
    return f"doctor-{uuid.uuid4().hex[:12]}@example.com"


async def register_test_doctor(
    db_session: AsyncSession,
    *,
    hospital_name: str = "Test General Hospital",
    email: str | None = None,
    password: str = "correct-horse-battery-staple",
    full_name: str = "Dr. Test Doctor",
) -> dict:
    """Creates a doctor row directly via the service layer, the same way an
    operator provisions one now that there is no self-service /auth/register
    endpoint (see app/api/auth.py, app/scripts/promote_admin.py). Returns
    the plaintext credentials so the caller can log in with them."""
    hospital = await get_or_create_hospital(db_session, hospital_name)
    email = email or _unique_email()
    await create_doctor(
        db_session, hospital_id=hospital.id, email=email, password=password, full_name=full_name
    )
    await db_session.commit()
    return {
        "hospital_name": hospital_name,
        "email": email,
        "password": password,
        "full_name": full_name,
    }


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


async def type_patient_and_donor_hla(
    patient_client: AsyncClient,
    patient_id: str,
    donor_id: str,
    donor_client: AsyncClient | None = None,
) -> None:
    """Fills in full A/B/DRB1 typing (COMPATIBLE_PATIENT_HLA/
    COMPATIBLE_DONOR_HLA) for both sides of a pair. POST /compatibility/
    check's completeness precondition (compute_hla_mismatch_result in
    compatibility_precondition_service.py) hard-blocks on any missing
    locus, so any test driving that endpoint needs this first even when
    HLA data isn't otherwise relevant to what it's testing (audit logging,
    dashboard listing, ...). donor_client defaults to patient_client;
    pass it explicitly for a cross-hospital donor owned by a different
    doctor (PUT .../hla-typings is ownership-scoped)."""
    await patient_client.put(f"/patients/{patient_id}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await (donor_client or patient_client).put(
        f"/donors/{donor_id}/hla-typings", json=COMPATIBLE_DONOR_HLA
    )

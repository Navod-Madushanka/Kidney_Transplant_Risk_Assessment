# app/tests/integration/test_ocr_startup.py
"""Coverage for the startup reconciliation added to app/main.py's lifespan
handler as part of the Part G bounded-memory pass: BackgroundTasks die
with the process, so an OcrExtractionJob left RUNNING at boot is
definitionally dead on a single-worker deployment -- see main.py's
lifespan docstring for the full reasoning.

Exercises `lifespan` directly rather than through the `client`/
`auth_client` fixtures: those are wired via httpx's ASGITransport, which
never triggers ASGI lifespan startup/shutdown events, so main.py's
reconciliation logic would otherwise never run in the test suite at all.
"""
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as fastapi_app
from app.main import lifespan
from app.models.enums import OcrExtractionJobStatus
from app.models.ocr_extraction_job import OcrExtractionJob


async def _create_job(
    db_session: AsyncSession, doctor_id: uuid.UUID, status: OcrExtractionJobStatus
) -> OcrExtractionJob:
    job = OcrExtractionJob(doctor_id=doctor_id, status=status, documents={})
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


async def test_running_job_marked_failed_on_startup(auth_client: AsyncClient, db_session):
    me = await auth_client.get("/auth/me")
    doctor_id = uuid.UUID(me.json()["id"])
    job = await _create_job(db_session, doctor_id, OcrExtractionJobStatus.RUNNING)

    async with lifespan(fastapi_app):
        pass

    await db_session.refresh(job)
    assert job.status == OcrExtractionJobStatus.FAILED
    assert job.error == "Server restarted during extraction. Please re-upload and try again."


async def test_done_job_untouched_on_startup(auth_client: AsyncClient, db_session):
    me = await auth_client.get("/auth/me")
    doctor_id = uuid.UUID(me.json()["id"])
    job = await _create_job(db_session, doctor_id, OcrExtractionJobStatus.DONE)

    async with lifespan(fastapi_app):
        pass

    await db_session.refresh(job)
    assert job.status == OcrExtractionJobStatus.DONE
    assert job.error is None

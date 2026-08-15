# app/main.py
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.audit_logs import router as audit_logs_router
from app.api.auth import router as auth_router
from app.api.compatibility import router as compatibility_router
from app.api.dashboard import router as dashboard_router
from app.api.donors import router as donors_router
from app.api.exchange import router as exchange_router
from app.api.ocr import router as ocr_router
from app.api.pairs import router as pairs_router
from app.api.patients import router as patients_router
from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.session import async_session_maker, get_db
from app.models.doctor import Doctor
from app.models.enums import OcrExtractionJobStatus
from app.models.ocr_extraction_job import OcrExtractionJob
from app.services.ocr_spool_service import sweep_stale_spools

_RESTART_ERROR_MESSAGE = "Server restarted during extraction. Please re-upload and try again."


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup reconciliation for the OCR extraction background-job
    pipeline (Part G, bounded memory for the extraction upload path):

    1. Sweeps spool directories orphaned by a hard crash — the try/finally
       in ocr_job_service.run_extraction_job handles cleanup on every
       normal exit path, but can't run if the process itself dies mid-job.
    2. Marks every OcrExtractionJob still RUNNING as FAILED. BackgroundTasks
       die with the process, so a job left RUNNING at boot is definitionally
       dead — without this it sits "running" forever while the frontend
       polls it every 2.5s indefinitely.

    Startup-only is sufficient: the try/finally handles the normal path and
    the process restarts on every deploy, so a periodic sweeper isn't worth
    an extra asyncio task here. Both of these inferences are only safe on a
    single-worker, single-host deployment — the moment `uvicorn` runs with
    `--workers` or the backend runs on more than one host, "RUNNING at
    boot" no longer implies "dead" (another worker's process may still own
    it), and this whole handler becomes wrong. See
    app/services/ocr_spool_service.py's module docstring for the same
    caveat on the spool directory itself.
    """
    settings = get_settings()
    sweep_stale_spools(settings.ocr_spool_max_age_hours)

    async with async_session_maker() as db:
        await db.execute(
            update(OcrExtractionJob)
            .where(OcrExtractionJob.status == OcrExtractionJobStatus.RUNNING)
            .values(status=OcrExtractionJobStatus.FAILED, error=_RESTART_ERROR_MESSAGE)
        )
        await db.commit()

    yield


app = FastAPI(title="Kidney Transplant Compatibility System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(donors_router)
app.include_router(pairs_router)
app.include_router(compatibility_router)
app.include_router(dashboard_router)
app.include_router(ocr_router)
app.include_router(audit_logs_router)
app.include_router(exchange_router)

@app.get("/")
def read_root():
    return {"status": "healthy", "message": "Backend is running!"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
async def health_check_db(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    value = result.scalar()
    return {"status": "ok", "result": value}


@app.get("/auth/me")
async def read_current_user(current_doctor: Doctor = Depends(get_current_user)):
    return {
        "id": str(current_doctor.id),
        "email": current_doctor.email,
        "full_name": current_doctor.full_name,
        "hospital_id": str(current_doctor.hospital_id),
    }

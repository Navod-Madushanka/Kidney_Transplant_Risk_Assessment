# app/services/ocr_job_service.py
"""Runs document-batch extraction as a server-owned background job instead
of over a single long-lived streaming HTTP request.

Previously (/ocr/extract-batch/stream), a doctor navigating away from the
photo-upload step mid-extraction lost every visible sign of progress —
the fetch itself kept running, but its progress lived only in that page
component's local state, so it vanished the moment the component
unmounted, and any result that arrived afterward wrote into the wizard
silently with the doctor none the wiser. A job row here means extraction
keeps running and reporting progress regardless of which page (if any)
the doctor is looking at, or whether their connection drops entirely —
see OcrExtractionJob's docstring.

Reuses ocr_batch_service.stream_batch_extraction completely unchanged —
same ProgressEvent/DocumentChunk generator the old NDJSON endpoint
consumed. Only the sink changed, from an HTTP stream to this job row.
"""
import uuid
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.models.enums import OcrExtractionJobStatus
from app.models.ocr_extraction_job import OcrExtractionJob
from app.schemas.antibody_profile import AntibodyProfileEntry
from app.services.antibody_profile_service import replace_patient_antibody_profiles
from app.services.ocr_batch_service import DocumentChunk, ProgressEvent, stream_batch_extraction

_EMPTY_DOCUMENT_RESULT = {
    "patient_details": {},
    "donor_details": {},
    "patient_hla": [],
    "donor_hla": [],
    "bead_specificity": [],
    "crossmatch": {},
    "errors": [],
}


def _initial_documents(slots: list[str]) -> dict:
    return {
        slot: {"status": "pending", "completed": 0, "total": 1, **_EMPTY_DOCUMENT_RESULT}
        for slot in slots
    }


async def create_extraction_job(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    files: dict[str, tuple[bytes, str, str]],
    patient_id: uuid.UUID | None = None,
) -> OcrExtractionJob:
    """Creates the job row up front (status=running, every requested slot
    pending) so GET .../jobs/{id} has something valid to return the moment
    the caller has the job_id back — even before the background task
    (scheduled separately by the route, after this returns) has had a
    chance to run at all.

    patient_id -- see OcrExtractionJob.patient_id's docstring. Only the
    registration-time bead-specificity call path passes this."""
    job = OcrExtractionJob(
        doctor_id=doctor_id,
        patient_id=patient_id,
        status=OcrExtractionJobStatus.RUNNING,
        documents=_initial_documents(list(files.keys())),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def run_extraction_job(job_id: uuid.UUID, files: dict[str, tuple[bytes, str, str]]) -> None:
    """The background task itself — runs AFTER the request that kicked it
    off has already returned a response, so it owns its own DB session
    rather than reusing the request-scoped one (which is closed by then).

    Per-document extraction failures are already caught inside
    stream_batch_extraction and surfaced as an error-bearing DocumentChunk
    rather than a raised exception, so the try/except here is a last-resort
    safety net for something going wrong in this function itself (e.g. a
    DB write failing) — without it, an unhandled exception in a FastAPI
    BackgroundTask is only logged, leaving the job stuck at "running"
    forever with no way for a polling client to ever learn it failed.
    """
    async with async_session_maker() as db:
        job = await db.get(OcrExtractionJob, job_id)
        if job is None:
            return  # job row gone (shouldn't happen outside manual DB surgery)

        try:
            async for event in stream_batch_extraction(files):
                documents = dict(job.documents)
                prior = documents.get(event.document_type, {})

                if isinstance(event, ProgressEvent):
                    documents[event.document_type] = {
                        **prior,
                        "status": "in_progress",
                        "completed": event.completed,
                        "total": event.total,
                    }
                elif isinstance(event, DocumentChunk):
                    total = prior.get("total", 1)
                    chunk_data = asdict(event)
                    chunk_data.pop("document_type")
                    documents[event.document_type] = {
                        "status": "done",
                        "completed": total,
                        "total": total,
                        **chunk_data,
                    }

                # Reassigning the whole dict (rather than mutating job.documents
                # in place) is what makes SQLAlchemy notice the column changed —
                # JSONB columns aren't change-tracked on in-place mutation.
                job.documents = documents
                await db.commit()

            if job.patient_id is not None:
                await _save_bead_specificity_if_present(db, job)

            job.status = OcrExtractionJobStatus.DONE
            await db.commit()
        except Exception as exc:
            await db.rollback()
            job.status = OcrExtractionJobStatus.FAILED
            job.error = str(exc)
            await db.commit()


async def _save_bead_specificity_if_present(db: AsyncSession, job: OcrExtractionJob) -> None:
    """Auto-saves whatever bead-specificity rows this job's pages produced,
    unattended -- unlike every other write to antibody_profiles, nobody is
    necessarily watching this job to review and PUT the results themselves
    (see NewPairPage.jsx, the only caller that passes patient_id today).
    ocr_verified=False always, regardless of what the pages contained, since
    a doctor hasn't seen this data yet -- see
    antibody_profile_service.replace_patient_antibody_profiles's
    _resolve_verified contract. Left inside run_extraction_job's own
    try/except, so a failure here correctly fails the whole job rather than
    reporting "done" with the save silently lost.

    Simple concatenation of both pages, same merge run_batch_extraction
    already does for the synchronous /extract-batch endpoint (see
    ocr_batch_service.py's `result.bead_specificity.extend(...)`)."""
    bead_rows = [
        *job.documents.get("bead_specificity_page_1", {}).get("bead_specificity", []),
        *job.documents.get("bead_specificity_page_2", {}).get("bead_specificity", []),
    ]
    if not bead_rows:
        return

    entries = [AntibodyProfileEntry(antigen=row["antigen"], mfi=row["mfi"]) for row in bead_rows]
    await replace_patient_antibody_profiles(
        db, job.patient_id, entries, ocr_verified=False, doctor_id=job.doctor_id
    )


async def get_extraction_job(
    db: AsyncSession, doctor_id: uuid.UUID, job_id: uuid.UUID
) -> OcrExtractionJob | None:
    """Scoped to the requesting doctor — a job_id alone shouldn't be enough
    to read another doctor's in-progress extraction."""
    result = await db.execute(
        select(OcrExtractionJob).where(
            OcrExtractionJob.id == job_id, OcrExtractionJob.doctor_id == doctor_id
        )
    )
    return result.scalar_one_or_none()

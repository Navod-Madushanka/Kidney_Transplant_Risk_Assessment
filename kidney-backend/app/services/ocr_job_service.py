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
import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_maker
from app.models.enums import OcrExtractionJobStatus
from app.models.ocr_extraction_job import OcrExtractionJob
from app.schemas.antibody_profile import AntibodyProfileEntry
from app.services.antibody_profile_service import replace_patient_antibody_profiles
from app.services.ocr_batch_service import (
    DocumentChunk,
    ProgressEvent,
    check_bead_id_uniqueness_across_pages,
    stream_batch_extraction,
)
from app.services.ocr_spool_service import SpooledUpload, discard_spool

_EMPTY_DOCUMENT_RESULT = {
    "patient_details": {},
    "donor_details": {},
    "patient_hla": [],
    "donor_hla": [],
    "bead_specificity": [],
    "crossmatch": {},
    "errors": [],
}

# Bounds how many jobs run their actual extraction calls concurrently
# (acquired around the extraction loop below, not the whole job) — shared
# across every call to run_extraction_job in this process, so it has to be
# a module-level singleton rather than something created per-call. See
# Settings.ocr_max_concurrent_jobs's docstring for why this defaults to 1:
# Ollama serializes inference regardless, so raising it doesn't add
# throughput, it only multiplies concurrent PIL decodes in ocr-service.
_extraction_semaphore = asyncio.Semaphore(get_settings().ocr_max_concurrent_jobs)

# Part H fix: asyncio.create_task's own result must be referenced
# somewhere until it finishes, or the event loop is free to garbage-collect
# it mid-execution -- see
# https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
# ("Important: Save a reference..."). This set is that reference; each
# task's done-callback discards itself once finished, so the set doesn't
# grow unbounded. Module-level for the same reason _extraction_semaphore
# is: one process-wide place, not something scoped to a single call.
_running_jobs: set[asyncio.Task] = set()


def _initial_documents(slot_names: Sequence[str]) -> dict:
    return {
        slot: {"status": "pending", "completed": 0, "total": 1, **_EMPTY_DOCUMENT_RESULT}
        for slot in slot_names
    }


async def create_extraction_job(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    slot_names: Sequence[str],
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
        documents=_initial_documents(slot_names),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def schedule_extraction_job(
    job_id: uuid.UUID, spool_dir: Path, files: dict[str, SpooledUpload]
) -> None:
    """Schedules run_extraction_job as an independent asyncio Task rather
    than via FastAPI's `BackgroundTasks.add_task` (which the route used
    before this existed).

    This is not a style choice -- it's required for run_extraction_job's
    own session-scoping fix (see its docstring) to actually work.
    BackgroundTasks execute INSIDE the request's outer AsyncExitStack, the
    same stack that closes every `Depends(..., yield ...)` dependency
    (FastAPI's `request_response` wrapper only exits `request_stack` AFTER
    `await response(scope, receive, send)` returns, and that call is what
    runs `response.background()`). Concretely: the request's own `db`
    session -- opened once via `Depends(get_db)` and shared by
    get_current_user and the route handler itself -- stayed checked out
    for the ENTIRE duration of the background task, on top of anything
    run_extraction_job did internally. Confirmed via
    test_ocr_job_db_sessions.py, which still saw one held connection per
    job with BackgroundTasks even after run_extraction_job's own session
    scoping was fixed. asyncio.create_task detaches the job from the
    request's lifecycle entirely, so that connection is released the
    moment the response is sent, same as any other request.
    """
    task = asyncio.create_task(run_extraction_job(job_id, spool_dir, files))
    _running_jobs.add(task)
    task.add_done_callback(_running_jobs.discard)


def _apply_event(documents: dict, event: ProgressEvent | DocumentChunk) -> dict:
    """Pure function: folds one ProgressEvent/DocumentChunk into a
    `documents` snapshot and returns the new dict. Extracted out of
    run_extraction_job so each event can be applied inside its own
    short-lived session (see that function's docstring for why) without
    duplicating this logic at each of the two call sites that used to be
    one inline block."""
    documents = dict(documents)
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

    return documents


async def run_extraction_job(
    job_id: uuid.UUID, spool_dir: Path, files: dict[str, SpooledUpload]
) -> None:
    """The background task itself — runs AFTER the request that kicked it
    off has already returned a response, so it owns its own DB session(s)
    rather than reusing the request-scoped one (which is closed by then).

    NEVER HOLD A SESSION ACROSS AN AWAIT ON OCR-SERVICE. A single extraction
    call/tile takes 1.5-3 minutes; a session held for that long checks out a
    pooled connection for the whole duration while doing nothing with it
    (`await db.commit()` ends the transaction, not the connection checkout
    — that only happens when the `async with` exits). With the default pool
    (5 + 10 overflow), roughly 15 concurrent jobs exhausts it, and every
    OTHER request — logins, patient lookups, even the 2.5s polling GETs —
    then queues behind `pool_timeout` and eventually 503s, which starves
    /health/db too and can trigger an orchestrator restart that kills every
    in-flight job. So each write below opens its own session immediately
    before the write and closes it immediately after — a `SELECT` + an
    `UPDATE` per event instead of one `UPDATE` per job, which is a few
    milliseconds against minutes of inference. Do not "optimise" this back
    into one session wrapping the loop.

    Re-fetching `job` fresh in every session is deliberate, not an
    oversight: `expire_on_commit=False` keeps attributes readable after a
    commit, but the instance stays bound to the session that loaded it —
    reusing it across sessions raises or silently no-ops. Each session
    below re-fetches by primary key rather than passing the previous
    session's instance around.

    Read-modify-write of `documents` is safe unsynchronized today because
    exactly one background task ever writes a given job row. If that stops
    being true, this needs `SELECT ... FOR UPDATE`.

    The extraction-concurrency semaphore is acquired around the loop below,
    OUTSIDE every session scope — acquiring it while holding a connection
    would let queued jobs pile up pooled connections while blocked on the
    semaphore, turning a transient squeeze into a guaranteed stall at a much
    lower concurrency than before. Land any future concurrency change with
    this ordering preserved, not before it.

    Per-document extraction failures are already caught inside
    stream_batch_extraction and surfaced as an error-bearing DocumentChunk
    rather than a raised exception, so the outer try/except is a
    last-resort safety net for something going wrong in this function
    itself (e.g. a DB write failing) — without it, an unhandled exception
    in a FastAPI BackgroundTask is only logged, leaving the job stuck at
    "running" forever with no way for a polling client to ever learn it
    failed. That except block opens a FRESH session rather than reusing (or
    rolling back) whatever session was active when the exception fired —
    if the failure was itself a pool timeout or a dead connection, the old
    session is exactly the thing that's unusable.

    The outer try/finally discards the job's spool directory (see
    app/services/ocr_spool_service.py) on every path out of this function
    — success, a per-document failure, or this function's own last-resort
    except below — so the uploaded images never outlive the job that
    needed them. This is the normal cleanup path; sweep_stale_spools (run
    at startup, see app/main.py) is only the backstop for a hard crash that
    skips this entirely.
    """
    try:
        async with async_session_maker() as db:
            if await db.get(OcrExtractionJob, job_id) is None:
                return  # job row gone (shouldn't happen outside manual DB surgery)

        try:
            async with _extraction_semaphore:
                async for event in stream_batch_extraction(files):
                    async with async_session_maker() as db:
                        job = await db.get(OcrExtractionJob, job_id)
                        if job is None:
                            return
                        # Reassigning the whole dict (rather than mutating
                        # job.documents in place) is what makes SQLAlchemy
                        # notice the column changed — JSONB columns aren't
                        # change-tracked on in-place mutation.
                        job.documents = _apply_event(job.documents, event)
                        await db.commit()

            async with async_session_maker() as db:
                job = await db.get(OcrExtractionJob, job_id)
                if job is None:
                    return
                if job.patient_id is not None:
                    await _save_bead_specificity_if_present(db, job)
                job.status = OcrExtractionJobStatus.DONE
                await db.commit()
        except Exception as exc:
            async with async_session_maker() as db:
                job = await db.get(OcrExtractionJob, job_id)
                if job is not None:
                    job.status = OcrExtractionJobStatus.FAILED
                    job.error = str(exc)
                    await db.commit()
    finally:
        discard_spool(spool_dir)


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

    Simple concatenation of both pages, same merge ocr_batch_service.py's
    run_batch_extraction already does (see its
    `result.bead_specificity.extend(...)`) -- reconciliation already ran
    PER PAGE inside ocr-service, where the tiles are; this must never
    dedupe again, only concatenate and verify. See
    ocr_batch_service.check_bead_id_uniqueness_across_pages's docstring
    for why (page, bead), not bead alone, is the real cross-page identity.

    Part I (null-MFI contract): AntibodyProfile.mfi is NOT NULL, so a row
    the model flagged as illegible (mfi=None, preserved deliberately by
    the prompt rather than dropped -- see ocr-service's
    BEAD_SPECIFICITY_PROMPT) is filtered out here before building entries,
    never allowed to raise a Pydantic/DB validation error that would fail
    this whole job. The doctor already learned about it: ocr-service's own
    "unreadable_mfi" structured warning (see llm_extract.py's
    _build_bead_warnings) is already attached to the document's errors,
    well before this function runs.
    """
    bead_rows = [
        *job.documents.get("bead_specificity_page_1", {}).get("bead_specificity", []),
        *job.documents.get("bead_specificity_page_2", {}).get("bead_specificity", []),
    ]
    if not bead_rows:
        return

    uniqueness_warnings = check_bead_id_uniqueness_across_pages(bead_rows)
    if uniqueness_warnings:
        documents = dict(job.documents)
        for slot in ("bead_specificity_page_1", "bead_specificity_page_2"):
            if slot not in documents:
                continue
            doc = dict(documents[slot])
            doc["errors"] = [*doc.get("errors", []), *uniqueness_warnings]
            documents[slot] = doc
        job.documents = documents  # reassign whole dict -- see the JSONB comment above

    readable_rows = [row for row in bead_rows if row.get("mfi") is not None]
    if not readable_rows:
        return

    entries = [
        AntibodyProfileEntry(
            antigen=row["antigen"],
            mfi=row["mfi"],
            bead_id=row.get("bead"),
            panel=row.get("panel"),
            extraction_conflict=row.get("conflict"),
        )
        for row in readable_rows
    ]
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

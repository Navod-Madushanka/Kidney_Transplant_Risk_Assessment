# app/api/ocr.py
import uuid
from pathlib import Path

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.ocr import (
    OcrExtractResponse,
    OcrJobCreateResponse,
    OcrJobStatusResponse,
)
from app.services.ocr_client import call_ocr_service
from app.services.ocr_job_service import (
    create_extraction_job,
    get_extraction_job,
    schedule_extraction_job,
)
from app.services.ocr_spool_service import SpooledUpload, discard_spool, spool_uploads
from app.services.patient_service import get_patient_by_id_for_doctor

router = APIRouter(prefix="/ocr", tags=["ocr"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


def _validate_file(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Only JPG and PNG are accepted.",
        )


async def _build_files_payload(
    hla_typing_report: UploadFile | None,
    crossmatch_report: UploadFile | None,
    bead_specificity_page_1: UploadFile | None,
    bead_specificity_page_2: UploadFile | None,
) -> tuple[Path, dict[str, SpooledUpload]]:
    # Order here is dispatch order (stream_batch_extraction iterates in
    # insertion order) — HLA typing first since it's the primary identity
    # source, crossmatch second since it's a fast single-shot call, bead
    # specificity pages last since they're by far the slowest (8 tiles
    # each). Phase 1 speed pass (2026-08-04): this puts the fastest/most
    # valuable fields in front of the doctor first rather than behind two
    # ~10min pages.
    slots = {
        "hla_typing_report": hla_typing_report,
        "crossmatch_report": crossmatch_report,
        "bead_specificity_page_1": bead_specificity_page_1,
        "bead_specificity_page_2": bead_specificity_page_2,
    }
    provided = {name: f for name, f in slots.items() if f is not None}

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image must be provided.",
        )

    for f in provided.values():
        _validate_file(f)

    # Streams each upload straight to local disk instead of reading it
    # fully into RAM — see app/services/ocr_spool_service.py. Raises 413
    # mid-stream on an oversized file, before anything is buffered.
    return await spool_uploads(provided)


@router.post(
    "/extract-batch/jobs",
    response_model=OcrJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_extract_batch_job(
    hla_typing_report: UploadFile | None = File(None),
    bead_specificity_page_1: UploadFile | None = File(None),
    bead_specificity_page_2: UploadFile | None = File(None),
    crossmatch_report: UploadFile | None = File(None),
    patient_id: uuid.UUID | None = Form(None),
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kicks off document-batch extraction as a background job instead of
    a request the caller has to stay connected for — bead specificity
    pages alone can take 1.5-3 min each, and the previous streaming
    endpoint (removed) tied that entire duration to one HTTP connection:
    navigating away mid-extraction didn't stop the work, but it did kill
    every visible sign of it, since progress lived only in the page
    component that made the request. See ocr_job_service.py.

    Scheduled via asyncio.create_task (ocr_job_service.schedule_extraction_job),
    not FastAPI's BackgroundTasks -- see that function's docstring for why
    that distinction actually matters here (it's not a style choice): with
    BackgroundTasks, this request's own `db` session stayed checked out
    for the job's entire multi-minute duration, regardless of anything
    run_extraction_job did internally.

    Returns a job_id immediately (202, before any extraction has actually
    happened) — poll GET /ocr/extract-batch/jobs/{job_id} for progress and
    results, from anywhere, at any pace. The job keeps running server-side
    regardless of whether anything is polling it.

    patient_id -- optional; scopes the job to a patient for audit purposes
    only (see OcrExtractionJob.patient_id's docstring -- Part J removed the
    unattended auto-save this used to authorise). Nothing in the current
    frontend sends it. Ownership is still checked here, before the job row
    is even created, same as the other upfront validation below -- a job
    tagged to a patient the requesting doctor doesn't own is refused
    regardless of what (if anything) it's ever used for.

    All upfront validation (at-least-one-file, content-type, patient
    ownership, and now the per-file size cap enforced while spooling to
    disk) happens before the job row is even created, so those failures
    still come back as a normal synchronous JSON error response — including
    a 413 for an oversized upload.
    """
    if patient_id is not None:
        patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    spool_dir, files = await _build_files_payload(
        hla_typing_report, crossmatch_report, bead_specificity_page_1, bead_specificity_page_2
    )

    try:
        job = await create_extraction_job(db, current_doctor.id, list(files), patient_id=patient_id)
    except Exception:
        discard_spool(spool_dir)
        raise
    schedule_extraction_job(job.id, spool_dir, files)

    return OcrJobCreateResponse(job_id=job.id)


@router.get("/extract-batch/jobs/{job_id}", response_model=OcrJobStatusResponse)
async def get_extract_batch_job(
    job_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await get_extraction_job(db, current_doctor.id, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extraction job not found")

    return OcrJobStatusResponse(
        job_id=job.id, status=job.status, documents=job.documents, error=job.error
    )


@router.post("/lab-report", response_model=OcrExtractResponse)
async def extract_lab_report(
    file: UploadFile = File(...),
    current_doctor: Doctor = Depends(get_current_user),
):
    """Kept for any existing single-image callers — now must pass a
    document_type through to the OCR service."""
    _validate_file(file)
    spool_dir, files = await spool_uploads({"hla_typing_report": file})
    try:
        result = await call_ocr_service(files["hla_typing_report"], "hla_typing_report")
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="OCR service timed out, please try again",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OCR service returned an error: {exc.response.status_code}",
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR service unavailable",
        )
    finally:
        discard_spool(spool_dir)

    return result["structured"]

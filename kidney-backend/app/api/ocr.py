# app/api/ocr.py
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.ocr import (
    OcrBatchExtractResponse,
    OcrExtractResponse,
    OcrJobCreateResponse,
    OcrJobStatusResponse,
)
from app.services.ocr_batch_service import run_batch_extraction
from app.services.ocr_client import call_ocr_service
from app.services.ocr_job_service import create_extraction_job, get_extraction_job, run_extraction_job

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
) -> dict[str, tuple[bytes, str, str]]:
    # Order here is dispatch order (stream_batch_extraction/
    # run_batch_extraction iterate in insertion order) — HLA typing first
    # since it's the primary identity source, crossmatch second since it's
    # a fast single-shot call, bead specificity pages last since they're by
    # far the slowest (8 tiles each). Phase 1 speed pass (2026-08-04): this
    # puts the fastest/most valuable fields in front of the doctor first
    # rather than behind two ~10min pages.
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

    files_payload = {}
    for name, f in provided.items():
        contents = await f.read()
        files_payload[name] = (contents, f.filename, f.content_type)

    return files_payload


@router.post("/extract-batch", response_model=OcrBatchExtractResponse)
async def extract_batch(
    hla_typing_report: UploadFile | None = File(None),
    bead_specificity_page_1: UploadFile | None = File(None),
    bead_specificity_page_2: UploadFile | None = File(None),
    crossmatch_report: UploadFile | None = File(None),
    current_doctor: Doctor = Depends(get_current_user),
):
    files_payload = await _build_files_payload(
        hla_typing_report, crossmatch_report, bead_specificity_page_1, bead_specificity_page_2
    )

    result = await run_batch_extraction(files_payload)

    return OcrBatchExtractResponse(
        patient_details=result.patient_details,
        donor_details=result.donor_details,
        patient_hla=result.patient_hla,
        donor_hla=result.donor_hla,
        bead_specificity=result.bead_specificity,
        crossmatch=result.crossmatch,
        errors=result.errors,
    )


@router.post(
    "/extract-batch/jobs",
    response_model=OcrJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_extract_batch_job(
    background_tasks: BackgroundTasks,
    hla_typing_report: UploadFile | None = File(None),
    bead_specificity_page_1: UploadFile | None = File(None),
    bead_specificity_page_2: UploadFile | None = File(None),
    crossmatch_report: UploadFile | None = File(None),
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

    Returns a job_id immediately (202, before any extraction has actually
    happened) — poll GET /ocr/extract-batch/jobs/{job_id} for progress and
    results, from anywhere, at any pace. The job keeps running server-side
    regardless of whether anything is polling it.

    All upfront validation (at-least-one-file, content-type) happens
    before the job row is even created, so those failures still come back
    as a normal synchronous JSON error response.
    """
    files_payload = await _build_files_payload(
        hla_typing_report, crossmatch_report, bead_specificity_page_1, bead_specificity_page_2
    )

    job = await create_extraction_job(db, current_doctor.id, files_payload)
    background_tasks.add_task(run_extraction_job, job.id, files_payload)

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
    contents = await file.read()

    try:
        result = await call_ocr_service(
            contents, file.filename, file.content_type, "hla_typing_report"
        )
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

    return result["structured"]

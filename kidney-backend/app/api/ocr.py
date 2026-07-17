# app/api/ocr.py
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.dependencies import get_current_user
from app.models.doctor import Doctor
from app.schemas.ocr import OcrExtractResponse, OcrBatchExtractResponse
from app.services.ocr_client import call_ocr_service
from app.services.ocr_batch_service import run_batch_extraction

router = APIRouter(prefix="/ocr", tags=["ocr"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


def _validate_file(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Only JPG and PNG are accepted.",
        )


@router.post("/extract-batch", response_model=OcrBatchExtractResponse)
async def extract_batch(
    hla_typing_report: UploadFile | None = File(None),
    bead_specificity_page_1: UploadFile | None = File(None),
    bead_specificity_page_2: UploadFile | None = File(None),
    crossmatch_report: UploadFile | None = File(None),
    current_doctor: Doctor = Depends(get_current_user),
):
    slots = {
        "hla_typing_report": hla_typing_report,
        "bead_specificity_page_1": bead_specificity_page_1,
        "bead_specificity_page_2": bead_specificity_page_2,
        "crossmatch_report": crossmatch_report,
    }
    provided = {name: f for name, f in slots.items() if f is not None}

    if not provided:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one image must be provided.")

    for f in provided.values():
        _validate_file(f)

    files_payload = {}
    for name, f in provided.items():
        contents = await f.read()
        files_payload[name] = (contents, f.filename, f.content_type)

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
        result = await call_ocr_service(contents, file.filename, file.content_type, "hla_typing_report")
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="OCR service timed out, please try again")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OCR service returned an error: {exc.response.status_code}")
    except httpx.HTTPError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OCR service unavailable")

    return result["structured"]
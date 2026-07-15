# app/api/ocr.py
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.dependencies import get_current_user
from app.models.doctor import Doctor
from app.schemas.ocr import OcrExtractResponse
from app.services.ocr_client import call_ocr_service

router = APIRouter(prefix="/ocr", tags=["ocr"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


@router.post("/lab-report", response_model=OcrExtractResponse)
async def extract_lab_report(
    file: UploadFile = File(...),
    current_doctor: Doctor = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Only JPG and PNG are accepted.",
        )

    contents = await file.read()

    try:
        result = await call_ocr_service(contents, file.filename, file.content_type)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="OCR service timed out, please try again",
        )
    except httpx.HTTPStatusError as exc:
        # OCR service responded but with an error (bad file, bad API key, etc.)
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
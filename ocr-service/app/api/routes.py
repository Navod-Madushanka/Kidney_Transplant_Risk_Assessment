from fastapi import APIRouter, UploadFile, File, Header, HTTPException, Request
import shutil
import uuid
import os

from app.core.config import settings
from app.extraction.demographics import extract_demographics
from app.extraction.hla import extract_hla

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

@router.post("/extract")
async def extract_report(
    request: Request,
    file: UploadFile = File(...),
    x_internal_api_key: str = Header(...),
) -> dict:
    # --- Security check first, before touching the file at all ---
    if x_internal_api_key != settings.ocr_service_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # --- Cheap validation before expensive OCR work ---
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Only JPG and PNG are accepted.",
        )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {settings.max_upload_size_mb}MB.",
        )

    # --- Save to a temp path so PaddleOCR (which expects a file path) can read it ---
    temp_filename = f"/tmp/{uuid.uuid4()}_{file.filename}"
    with open(temp_filename, "wb") as f:
        f.write(contents)

    try:
        ocr_engine = request.app.state.ocr_engine
        raw_result = ocr_engine.extract_raw(temp_filename)
        structured = extract_demographics(raw_result["rec_texts"], raw_result["rec_boxes"].tolist())
        hla = extract_hla(raw_result["rec_texts"], raw_result["rec_boxes"].tolist())
    finally:
        os.remove(temp_filename)  # always clean up, even if OCR raised an error

    return {
        "structured": {
            **structured,
            **hla,
        },
        "raw": {
            "texts": raw_result["rec_texts"],
            "scores": raw_result["rec_scores"],
            "boxes": raw_result["rec_boxes"].tolist(),
        },
    }
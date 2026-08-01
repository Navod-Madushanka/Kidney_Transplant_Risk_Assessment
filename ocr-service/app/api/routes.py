# app/api/routes.py
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException

from app.core.config import settings
from app.extraction.llm_extract import extract_bead_specificity, extract_crossmatch, extract_hla_typing
from app.llm.client import LLMExtractionError

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
VALID_DOCUMENT_TYPES = {"hla_typing_report", "bead_specificity", "crossmatch"}


async def _run_extraction(document_type: str, image_bytes: bytes) -> dict:
    if document_type == "hla_typing_report":
        return await extract_hla_typing(image_bytes)
    if document_type == "bead_specificity":
        return await extract_bead_specificity(image_bytes)
    if document_type == "crossmatch":
        return await extract_crossmatch(image_bytes)
    raise ValueError(f"Unhandled document_type: {document_type}")


@router.post("/extract")
async def extract_report(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    x_internal_api_key: str = Header(...),
) -> dict:
    if x_internal_api_key != settings.ocr_service_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid document_type: {document_type}. Must be one of {sorted(VALID_DOCUMENT_TYPES)}.",
        )

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

    # No more temp-file-on-disk step — that existed only because PaddleOCR's
    # predict() took a file path. The LLM client works directly off the
    # in-memory bytes (base64-encoded for the Ollama request), so this is a
    # straight simplification, not a functional change.
    try:
        structured = await _run_extraction(document_type, contents)
    except LLMExtractionError as exc:
        # Hard failure (Ollama unreachable, model missing, or never returned
        # valid JSON even after a retry) — this is the same failure class
        # kidney-backend's ocr_client.py already handles as a 502/503/504,
        # so surface it as a real HTTP error rather than a silent empty
        # result. Soft/partial extraction issues (a locus the validator
        # rejected, a bead-specificity tile that degenerated) stay inside
        # structured["warning"] instead — see app/extraction/llm_extract.py.
        raise HTTPException(status_code=502, detail=f"OCR extraction failed: {exc}") from exc

    return {
        "document_type": document_type,
        "structured": structured,
        # `raw` previously carried PaddleOCR's per-box texts/boxes/scores.
        # Confirmed via grep against kidney-backend and kidney-frontend
        # (2026-08-01): nothing reads any of those fields, so this is safe
        # to repurpose rather than needing to fabricate equivalents.
        "raw": {"model": settings.ollama_model},
    }

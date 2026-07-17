# app/api/routes.py
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, Request
import shutil
import uuid
import os

from app.core.config import settings
from app.extraction.demographics import extract_demographics
from app.extraction.hla import extract_hla
from app.extraction.mfi_extraction import extract_mfi_table
from app.extraction.crossmatch_extraction import extract_crossmatch

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
VALID_DOCUMENT_TYPES = {"hla_typing_report", "bead_specificity", "crossmatch"}


def _run_extraction(document_type: str, texts: list[str], boxes: list[list[int]]) -> dict:
    if document_type == "hla_typing_report":
        structured = extract_demographics(texts, boxes)
        structured.update(extract_hla(texts, boxes))
        return structured
    if document_type == "bead_specificity":
        return extract_mfi_table(texts, boxes)
    if document_type == "crossmatch":
        return extract_crossmatch(texts, boxes)
    raise ValueError(f"Unhandled document_type: {document_type}")


@router.post("/extract")
async def extract_report(
    request: Request,
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

    temp_filename = f"/tmp/{uuid.uuid4()}_{file.filename}"
    with open(temp_filename, "wb") as f:
        f.write(contents)

    try:
        ocr_engine = request.app.state.ocr_engine
        raw_result = ocr_engine.extract_raw(temp_filename)
        texts = raw_result["rec_texts"]
        boxes = raw_result["rec_boxes"].tolist()
        structured = _run_extraction(document_type, texts, boxes)
    finally:
        os.remove(temp_filename)

    return {
        "document_type": document_type,
        "structured": structured,
        "raw": {
            "texts": texts,
            "scores": raw_result["rec_scores"],
            "boxes": boxes,
        },
    }
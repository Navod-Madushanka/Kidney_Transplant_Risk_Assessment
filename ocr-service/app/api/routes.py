# app/api/routes.py
import json

from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.extraction.llm_extract import (
    extract_bead_specificity,
    extract_bead_specificity_stream,
    extract_crossmatch,
    extract_hla_typing,
)
from app.llm.client import LLMExtractionError

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
VALID_DOCUMENT_TYPES = {"hla_typing_report", "bead_specificity", "crossmatch"}

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


async def _run_extraction(document_type: str, image_bytes: bytes) -> dict:
    if document_type == "hla_typing_report":
        return await extract_hla_typing(image_bytes)
    if document_type == "bead_specificity":
        return await extract_bead_specificity(image_bytes)
    if document_type == "crossmatch":
        return await extract_crossmatch(image_bytes)
    raise ValueError(f"Unhandled document_type: {document_type}")


async def _authorize_and_read(
    file: UploadFile, document_type: str, x_internal_api_key: str
) -> bytes:
    """Shared upfront validation for both /extract and /extract/stream —
    auth, document_type, content-type, and size checks all raise a normal
    HTTPException, so they're done here BEFORE a streaming response ever
    starts (once StreamingResponse begins, failures can no longer come back
    as a clean JSON error body).

    The size cap is enforced WHILE reading, not after: reading the whole
    body first and comparing its length against max_bytes only rejects a
    cap that's already been blown, since by the time that comparison runs
    the oversized body is already fully resident. kidney-backend's own
    upload cap (Settings.ocr_upload_max_size_mb) already rejects anything
    this large before this service ever sees it in normal operation, but
    this endpoint is reachable directly too, so it has to enforce its own
    cap rather than relying on the caller's.
    """
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

    # Cheap pre-check when Starlette's multipart parser populated it —
    # doesn't replace the running-total check below, since `.size` can be
    # None.
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {settings.max_upload_size_mb}MB.",
        )

    chunks = []
    total = 0
    while chunk := await file.read(_CHUNK_SIZE):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size is {settings.max_upload_size_mb}MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/extract")
async def extract_report(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    x_internal_api_key: str = Header(...),
) -> dict:
    contents = await _authorize_and_read(file, document_type, x_internal_api_key)

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


@router.post("/extract/stream")
async def extract_report_stream(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    x_internal_api_key: str = Header(...),
):
    """Streaming variant of /extract, for bead_specificity only — the one
    document type slow enough (8 sequential vision-model calls, 1.5-3 min
    a page) that a caller waiting on a single request/response round trip
    has no way to show real progress. Yields NDJSON lines: one
    {"type": "progress", "completed": N, "total": 8} per tile completion
    (starting at N=0 before any tile has run), then a final
    {"type": "result", "document_type": ..., "structured": {...}, "raw":
    {...}} in the same shape /extract returns. kidney-backend's
    ocr_client.call_ocr_service_stream is the only caller today; HLA
    typing/crossmatch are single LLM calls with no intermediate signal to
    report, so they stay on /extract.
    """
    # Auth/content-type/size checks happen first, same order /extract uses
    # — an unauthenticated or malformed request shouldn't get a different
    # error just because it also picked the wrong document_type.
    contents = await _authorize_and_read(file, document_type, x_internal_api_key)

    if document_type != "bead_specificity":
        raise HTTPException(
            status_code=422,
            detail="/extract/stream only supports document_type=bead_specificity; use /extract for others.",
        )

    async def _generate():
        # No try/except around the tile loop here: _run_tile inside
        # extract_bead_specificity_stream already catches LLMExtractionError
        # per-tile (a bad tile becomes a None result + a failed-tile count
        # in the final warning, not a raised exception) — see that
        # function's docstring. If ocr-service dies mid-stream some other
        # way, the connection just drops; kidney-backend's
        # stream_batch_extraction already wraps its whole call to
        # call_ocr_service_stream in a try/except and turns that into a
        # per-document error chunk instead of failing the whole batch.
        async for event in extract_bead_specificity_stream(contents):
            if event["type"] == "progress":
                yield json.dumps(
                    {"type": "progress", "completed": event["completed"], "total": event["total"]}
                ) + "\n"
            else:
                yield json.dumps(
                    {
                        "type": "result",
                        "document_type": document_type,
                        "structured": event["structured"],
                        "raw": {"model": settings.ollama_model},
                    }
                ) + "\n"

    return StreamingResponse(
        _generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

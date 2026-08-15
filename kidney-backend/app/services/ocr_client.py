# app/services/ocr_client.py
import json
from typing import AsyncIterator

import httpx

from app.core.config import get_settings
from app.services.ocr_spool_service import SpooledUpload


async def call_ocr_service(
    upload: SpooledUpload, document_type: str, extra_data: dict | None = None
) -> dict:
    settings = get_settings()
    timeout = httpx.Timeout(settings.ocr_service_timeout_seconds, connect=5.0)
    data = {"document_type": document_type, **(extra_data or {})}
    # Streams the spooled file off disk instead of holding it in RAM --
    # httpx reads a plain (sync) file object in chunks on the event loop,
    # which is immaterial at local-disk speeds; see ocr_spool_service.py.
    with upload.path.open("rb") as fh:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.ocr_service_url}/extract",
                headers={"X-Internal-API-Key": settings.ocr_service_api_key},
                data=data,
                files={"file": (upload.filename, fh, upload.content_type)},
            )
            response.raise_for_status()
            return response.json()


async def call_ocr_service_stream(
    upload: SpooledUpload, document_type: str, extra_data: dict | None = None
) -> AsyncIterator[dict]:
    """Streaming variant of call_ocr_service — only ocr-service's
    /extract/stream route (bead_specificity only, see its docstring)
    supports this. Bead specificity pages are the one document type slow
    enough (8 sequential vision-model calls, 1.5-3 min a page) that a
    caller waiting on a single request/response round trip has no way to
    show real progress.

    extra_data -- merged into the multipart form body alongside
    document_type. Its one real use today: ocr_batch_service.py passes
    `dsa_band_edges` here for bead_specificity calls, so ocr-service's
    tile-reconciliation conflict rule can know where the real DSA
    clinical-severity thresholds fall without this service copy-pasting
    them (see ocr-service's bead_reconciliation._clinical_band docstring
    for why that matters -- kidney-backend OWNS those numbers, and a
    copy-pasted second copy could silently drift).

    Reads the response body as it arrives (httpx's streaming API, not
    client.post()'s buffer-the-whole-thing-then-return) and yields each
    NDJSON line parsed as a dict — either {"type": "progress", ...} or
    {"type": "result", ...}, unmodified from what ocr-service sent.
    stream_batch_extraction interprets them.
    """
    settings = get_settings()
    timeout = httpx.Timeout(settings.ocr_service_timeout_seconds, connect=5.0)
    data = {"document_type": document_type, **(extra_data or {})}
    # The file handle has to stay open for the ENTIRE streamed response --
    # the request body is consumed lazily, so this `with` wraps the whole
    # `async with client.stream(...)` block below, not just the call that
    # creates it. Closing it early gives a truncated or empty multipart
    # body with no obvious error. (No retry exists on this path today; if
    # one is ever added, re-open or seek(0) first -- retrying on an
    # already-consumed handle silently uploads zero bytes.)
    with upload.path.open("rb") as fh:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.ocr_service_url}/extract/stream",
                headers={"X-Internal-API-Key": settings.ocr_service_api_key},
                data=data,
                files={"file": (upload.filename, fh, upload.content_type)},
            ) as response:
                response.raise_for_status()
                buffer = ""
                async for text_chunk in response.aiter_text():
                    buffer += text_chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            yield json.loads(line)
                trailing = buffer.strip()
                if trailing:
                    yield json.loads(trailing)

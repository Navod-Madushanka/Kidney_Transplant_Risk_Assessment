# app/services/ocr_client.py
import json
from typing import AsyncIterator

import httpx

from app.core.config import get_settings


async def call_ocr_service(
    file_bytes: bytes, filename: str, content_type: str, document_type: str
) -> dict:
    settings = get_settings()
    timeout = httpx.Timeout(settings.ocr_service_timeout_seconds, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.ocr_service_url}/extract",
            headers={"X-Internal-API-Key": settings.ocr_service_api_key},
            data={"document_type": document_type},
            files={"file": (filename, file_bytes, content_type)},
        )
        response.raise_for_status()
        return response.json()


async def call_ocr_service_stream(
    file_bytes: bytes, filename: str, content_type: str, document_type: str
) -> AsyncIterator[dict]:
    """Streaming variant of call_ocr_service — only ocr-service's
    /extract/stream route (bead_specificity only, see its docstring)
    supports this. Bead specificity pages are the one document type slow
    enough (8 sequential vision-model calls, 1.5-3 min a page) that a
    caller waiting on a single request/response round trip has no way to
    show real progress.

    Reads the response body as it arrives (httpx's streaming API, not
    client.post()'s buffer-the-whole-thing-then-return) and yields each
    NDJSON line parsed as a dict — either {"type": "progress", ...} or
    {"type": "result", ...}, unmodified from what ocr-service sent.
    stream_batch_extraction interprets them.
    """
    settings = get_settings()
    timeout = httpx.Timeout(settings.ocr_service_timeout_seconds, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{settings.ocr_service_url}/extract/stream",
            headers={"X-Internal-API-Key": settings.ocr_service_api_key},
            data={"document_type": document_type},
            files={"file": (filename, file_bytes, content_type)},
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

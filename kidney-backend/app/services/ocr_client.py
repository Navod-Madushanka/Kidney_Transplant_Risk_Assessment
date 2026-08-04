# app/services/ocr_client.py
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

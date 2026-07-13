# backend: app/services/ocr_client.py
import httpx
from app.core.config import settings  # wherever your backend loads env vars

async def call_ocr_service(file_bytes: bytes, filename: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "http://localhost:8001/health",  # temporary — just proving connectivity
            headers={"X-Internal-API-Key": settings.OCR_SERVICE_API_KEY},
        )
        response.raise_for_status()
        return response.json()
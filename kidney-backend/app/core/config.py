# app/core/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    # Reserved for future use (e.g. caching, rate limiting, session storage).
    # Provisioned in local setup but not read anywhere in the app yet — see
    # the roadmap's Phase 1 note before adding a new use for it.
    redis_url: str
    secret_key: str
    environment: str = "local"

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # OCR service
    ocr_service_url: str = "http://localhost:8001"
    ocr_service_api_key: str
    # This used to be 120s (a PaddleOCR-era leftover), then 400s — enough
    # for a single hla_typing_report/crossmatch call (ocr-service's own
    # per-call budget is 180s, up to 360s with its one JSON retry — see
    # app/llm/client.py::REQUEST_TIMEOUT_SECONDS in ocr-service). 400s was
    # NOT enough for bead_specificity: that document type tiles the image
    # and runs each tile as its own sequential LLM call (tile concurrency
    # is deliberately bounded to 1 — see ocr-service's
    # llm_extract.py::CONCURRENT_TILE_LIMIT), so its real budget is
    # per-tile-budget x tile-count, not a single call's budget. Confirmed
    # 2026-08-03 on the dev RTX 2060: even after cutting tile count 8 -> 6
    # (ocr-service's tiling.py::DEFAULT_NUM_TILES) and fixing a real
    # GPU-underutilization bug, a single bead_specificity page still took
    # 402s end-to-end — already past the old 400s ceiling — with
    # individual tiles observed up to ~3 min each. Raised to 1200s (20min)
    # to give real headroom for slower runs (~3min/tile x 6 tiles + margin)
    # without being so tight it risks the same silent-failure problem on a
    # bad run. This is a shared ceiling across all document types, not
    # bead_specificity-specific — a genuinely hung hla_typing_report/
    # crossmatch call now also takes longer to be detected as failed;
    # revisit with a per-document-type timeout if that becomes a problem.
    ocr_service_timeout_seconds: float = 1200.0

    # Report file uploads (lab documents attached to patient/donor records)
    report_files_storage_dir: str = "uploads/report_files"
    report_files_max_size_mb: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()

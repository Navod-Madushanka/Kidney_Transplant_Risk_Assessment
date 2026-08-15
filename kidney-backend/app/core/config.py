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

    # SQLAlchemy engine `echo` -- logs every statement AND its bound
    # parameters. Was hardcoded True in app/db/session.py; flip to True
    # locally when you actually need to see the SQL, never leave it on.
    # Part H fix: with it on, every OcrExtractionJob write logs the full
    # `documents` JSONB blob (which only grows as bead rows accumulate) on
    # each of 16+ commits per extraction job -- disk and latency cost for
    # no benefit once you're not actively debugging.
    sql_echo: bool = False

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
    # individual tiles observed up to ~3 min each. This is a shared ceiling
    # across all document types, not bead_specificity-specific — a
    # genuinely hung hla_typing_report/crossmatch call now also takes
    # longer to be detected as failed; revisit with a per-document-type
    # timeout if that becomes a problem.
    #
    # Lowered from 1200s to 600s as part of the Part G bounded-memory pass:
    # with ocr_max_concurrent_jobs=1 (below), a stuck job blocks every other
    # queued job's documents at "pending" for up to this long. 600s is ~6x
    # the worst legitimate bead page (~100s/tile x 6 tiles), which still
    # gives real headroom for a slow run while halving the worst-case
    # head-of-line block a 1200s ceiling would allow.
    ocr_service_timeout_seconds: float = 600.0

    # Report file uploads (lab documents attached to patient/donor records)
    report_files_storage_dir: str = "uploads/report_files"
    report_files_max_size_mb: int = 20

    # OCR upload spooling (Part G, bounded memory for the extraction upload
    # path) — uploaded document images are streamed to local disk instead of
    # read fully into RAM, then streamed from disk to ocr-service. See
    # app/services/ocr_spool_service.py.
    #
    # Deliberately its own directory, NOT report_files_storage_dir: that one
    # holds permanent clinical attachments: this one is ephemeral spool
    # space swept on a timer (ocr_spool_max_age_hours) and after every job.
    # Never mix the two lifecycles in one tree.
    ocr_spool_dir: str = "uploads/ocr_spool"
    # Must stay equal to ocr-service's own Settings.max_upload_size_mb (see
    # ocr-service/app/core/config.py) — if this accepts more than
    # ocr-service allows, the upload succeeds, the job starts, and then
    # dies mid-extraction with a 413 the doctor can't act on. 15MB (not the
    # 10MB ocr-service used to default to) because a 300dpi A4 scan of a
    # bead-specificity chart is legitimately 3-6MB, and rejecting a real
    # report is a clinical workflow failure, not a nuisance.
    ocr_upload_max_size_mb: int = 15
    # Sweep cutoff for orphaned spool directories (crash recovery — see
    # app/services/ocr_spool_service.py::sweep_stale_spools and the startup
    # reconciliation in app/main.py). Comfortably exceeds the longest
    # plausible job (~10 min at today's ocr_service_timeout_seconds).
    ocr_spool_max_age_hours: float = 6.0
    # Bounds concurrent extraction jobs in-process. Default 1: Ollama
    # serializes inference regardless of how many requests hit it, so
    # raising this doesn't increase throughput — it only multiplies
    # concurrent PIL decodes in ocr-service (a 12MP photo is ~36MB resident
    # as a decoded bitmap), which is the exact peak-memory allocation this
    # setting exists to bound. Do not raise this to "speed things up".
    ocr_max_concurrent_jobs: int = 1

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()

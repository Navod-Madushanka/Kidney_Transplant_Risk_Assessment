# app/services/ocr_spool_service.py
"""Spools OCR-extraction uploads to local disk instead of reading them
fully into RAM. See the Part G bounded-memory implementation notes for the
full rationale: a phone photo decodes to roughly 10x its JPEG size once
ocr-service loads it into PIL, and a multi-document job used to hold every
uploaded file's bytes in memory for the whole extraction (minutes), not
just the request.

Deliberately local disk, not object storage: kidney-backend runs as one
uvicorn process on one host today, and app/services/report_file_service.py
already persists uploads the same way — same server-generated-filename,
cap-during-the-stream pattern, reused here rather than reinvented. The day
uvicorn gets `--workers`, or the backend runs on more than one host, this
(and the in-process semaphore in ocr_job_service.py) both become wrong —
that is the trigger to revisit, not before.
"""
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

_CHUNK_SIZE = 1024 * 1024  # 1 MiB

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


@dataclass(frozen=True)
class SpooledUpload:
    path: Path
    filename: str  # server-generated, e.g. "hla_typing_report.jpg"
    content_type: str


def _spool_root() -> Path:
    return Path(get_settings().ocr_spool_dir)


async def spool_uploads(slots: dict[str, UploadFile]) -> tuple[Path, dict[str, SpooledUpload]]:
    """Streams each upload in `slots` to <ocr_spool_dir>/<uuid4hex>/, one
    file per job (not per file), and returns (spool_dir, {slot: SpooledUpload}).
    One directory per job makes cleanup a single rmtree — no per-file
    bookkeeping, no partial-cleanup states.

    Raises 413 mid-stream if any file exceeds ocr_upload_max_size_mb — the
    running total is checked as each chunk is written, never after the
    whole file is buffered, so an oversized upload can't be used to force
    unbounded memory or disk use. On ANY failure (413 or otherwise), the
    whole spool_dir is removed before re-raising, so no partial write ever
    survives to be picked up by a background job.
    """
    settings = get_settings()
    max_size_bytes = settings.ocr_upload_max_size_mb * 1024 * 1024

    spool_dir = _spool_root() / uuid.uuid4().hex
    spool_dir.mkdir(parents=True, exist_ok=True)

    try:
        spooled: dict[str, SpooledUpload] = {}
        for slot, upload in slots.items():
            spooled[slot] = await _spool_one(upload, slot, spool_dir, max_size_bytes)
        return spool_dir, spooled
    except Exception:
        discard_spool(spool_dir)
        raise


async def _spool_one(
    upload: UploadFile, slot: str, spool_dir: Path, max_size_bytes: int
) -> SpooledUpload:
    # Cheap pre-check when Starlette's multipart parser populated it
    # (FastAPI >=0.115) — doesn't replace the running-total check below,
    # since `.size` can be None.
    max_mb = get_settings().ocr_upload_max_size_mb
    if upload.size is not None and upload.size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"{slot} exceeds the {max_mb}MB limit.",
        )

    # Content-type is validated by the caller before spooling starts (see
    # app/api/ocr.py's _validate_file), so this is always a hit.
    ext = _EXTENSION_BY_CONTENT_TYPE[upload.content_type]
    path = spool_dir / f"{slot}{ext}"

    size = 0
    with path.open("wb") as out:
        while chunk := await upload.read(_CHUNK_SIZE):
            size += len(chunk)
            if size > max_size_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"{slot} exceeds the {max_mb}MB limit.",
                )
            out.write(chunk)

    return SpooledUpload(path=path, filename=path.name, content_type=upload.content_type)


def discard_spool(spool_dir: Path) -> None:
    """Removes the whole spool directory. Never raises — a cleanup failure
    is a log line, never something that should fail a job that otherwise
    succeeded: extracted clinical data is never discarded because a
    directory wouldn't delete."""
    shutil.rmtree(spool_dir, ignore_errors=True)


def sweep_stale_spools(max_age_hours: float) -> int:
    """Removes spool directories whose mtime is older than the cutoff.
    Returns the count removed.

    This is the crash backstop for the try/finally in
    ocr_job_service.run_extraction_job, which can't run if the process
    dies mid-job — called once at startup (see app/main.py's lifespan
    handler), not on a recurring timer. The try/finally handles the normal
    path and the process restarts on every deploy, so a periodic sweeper
    isn't worth an extra asyncio task here.
    """
    root = _spool_root()
    if not root.exists():
        return 0

    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for entry in root.iterdir():
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed

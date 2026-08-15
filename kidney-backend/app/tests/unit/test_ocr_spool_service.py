# app/tests/unit/test_ocr_spool_service.py
"""Unit coverage for app/services/ocr_spool_service.py -- the Part G
bounded-memory pass that streams OCR-extraction uploads straight to local
disk instead of reading them fully into RAM. monkeypatches get_settings()
directly rather than relying on env vars, so each test can point
ocr_spool_dir at its own tmp_path and vary ocr_upload_max_size_mb freely.
"""
import io
import os
import time
from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.services import ocr_spool_service
from app.services.ocr_spool_service import discard_spool, spool_uploads, sweep_stale_spools


@dataclass
class _FakeSettings:
    ocr_spool_dir: str
    ocr_upload_max_size_mb: int = 15


def _use_spool_dir(monkeypatch, tmp_path, max_size_mb: int = 15) -> None:
    monkeypatch.setattr(
        ocr_spool_service, "get_settings", lambda: _FakeSettings(str(tmp_path), max_size_mb)
    )


def _make_upload(content: bytes, content_type: str, size: int | None = "auto") -> UploadFile:
    if size == "auto":
        size = len(content)
    return UploadFile(
        file=io.BytesIO(content),
        size=size,
        filename="whatever-the-client-called-it.jpg",
        headers=Headers({"content-type": content_type}),
    )


async def test_spools_one_file_per_slot_with_server_generated_filenames(monkeypatch, tmp_path):
    _use_spool_dir(monkeypatch, tmp_path)
    slots = {
        "hla_typing_report": _make_upload(b"hla bytes", "image/jpeg"),
        "crossmatch_report": _make_upload(b"crossmatch bytes", "image/png"),
    }

    spool_dir, spooled = await spool_uploads(slots)

    assert spool_dir.parent == tmp_path
    assert spool_dir.exists()
    # Server-generated from the slot name + content-type, never the
    # client-supplied filename ("whatever-the-client-called-it.jpg" above).
    assert spooled["hla_typing_report"].filename == "hla_typing_report.jpg"
    assert spooled["hla_typing_report"].content_type == "image/jpeg"
    assert spooled["hla_typing_report"].path.read_bytes() == b"hla bytes"
    assert spooled["crossmatch_report"].filename == "crossmatch_report.png"
    assert spooled["crossmatch_report"].path.read_bytes() == b"crossmatch bytes"
    assert {p.name for p in spool_dir.iterdir()} == {
        "hla_typing_report.jpg",
        "crossmatch_report.png",
    }


async def test_oversized_upload_raises_413_and_leaves_no_partial_directory(monkeypatch, tmp_path):
    _use_spool_dir(monkeypatch, tmp_path, max_size_mb=1)
    max_bytes = 1 * 1024 * 1024
    oversized = b"x" * (max_bytes * 2)
    # size=None forces the running-total path during the chunked read,
    # rather than the cheap upfront `.size` pre-check.
    slots = {"hla_typing_report": _make_upload(oversized, "image/jpeg", size=None)}

    with pytest.raises(HTTPException) as exc_info:
        await spool_uploads(slots)

    assert exc_info.value.status_code == 413
    # The whole job directory is gone, not just the offending file --
    # spool_uploads discards the entire spool_dir on any failure.
    assert list(tmp_path.iterdir()) == []


async def test_oversized_upload_caught_by_cheap_size_precheck(monkeypatch, tmp_path):
    # Same outcome as above, but via the `.size` pre-check (populated by
    # Starlette's multipart parser in real requests) rather than the
    # running-total fallback.
    _use_spool_dir(monkeypatch, tmp_path, max_size_mb=1)
    oversized = b"x" * (2 * 1024 * 1024)
    slots = {"hla_typing_report": _make_upload(oversized, "image/jpeg")}

    with pytest.raises(HTTPException) as exc_info:
        await spool_uploads(slots)

    assert exc_info.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_discard_spool_removes_the_whole_tree(tmp_path):
    spool_dir = tmp_path / "a-job"
    spool_dir.mkdir()
    (spool_dir / "hla_typing_report.jpg").write_bytes(b"data")

    discard_spool(spool_dir)

    assert not spool_dir.exists()


def test_discard_spool_does_not_raise_on_a_missing_path(tmp_path):
    discard_spool(tmp_path / "never-existed")  # must not raise


async def test_sweep_removes_stale_dirs_and_keeps_fresh_ones(monkeypatch, tmp_path):
    _use_spool_dir(monkeypatch, tmp_path)
    stale = tmp_path / "stale-job"
    stale.mkdir()
    fresh = tmp_path / "fresh-job"
    fresh.mkdir()

    cutoff_hours = 6.0
    old_mtime = time.time() - (cutoff_hours + 1) * 3600
    os.utime(stale, (old_mtime, old_mtime))

    removed = sweep_stale_spools(cutoff_hours)

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()


async def test_sweep_on_a_missing_root_returns_zero_without_raising(monkeypatch, tmp_path):
    _use_spool_dir(monkeypatch, tmp_path / "does-not-exist-yet")

    assert sweep_stale_spools(6.0) == 0

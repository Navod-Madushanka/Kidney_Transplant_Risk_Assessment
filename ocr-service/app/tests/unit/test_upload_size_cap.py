# app/tests/unit/test_upload_size_cap.py
#
# Covers _authorize_and_read's cap-before-read fix (Part G, bounded memory
# for the extraction upload path, kidney-backend side): the old
# implementation read the WHOLE upload into memory first and only checked
# its size afterward, so the 413 that's supposed to protect this service
# only fired once the damage (an unbounded read) was already done. This
# confirms the cap is enforced progressively, while chunks are still
# arriving, not after the full body has been buffered.
import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.api.routes import _authorize_and_read
from app.core.config import settings


class _CountingBytesIO(io.BytesIO):
    """Wraps BytesIO so a test can assert how much was actually pulled off
    it -- proves _authorize_and_read stopped reading once the cap was
    blown, rather than draining the rest of the stream first."""

    def __init__(self, data: bytes):
        super().__init__(data)
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.bytes_read += len(chunk)
        return chunk


def _make_upload(content: bytes) -> UploadFile:
    return UploadFile(
        file=_CountingBytesIO(content),
        size=None,  # force the running-total path, not the cheap .size pre-check
        filename="report.jpg",
        headers=Headers({"content-type": "image/jpeg"}),
    )


async def test_oversized_upload_is_rejected_before_the_whole_body_is_read(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    max_bytes = 1 * 1024 * 1024
    # 3x the cap -- if the fix regresses back to read-then-check, the
    # entire body gets pulled into memory before the 413 fires.
    oversized = b"x" * (max_bytes * 3)
    upload = _make_upload(oversized)

    with pytest.raises(HTTPException) as exc_info:
        await _authorize_and_read(upload, "hla_typing_report", settings.ocr_service_api_key)

    assert exc_info.value.status_code == 413
    underlying = upload.file
    assert isinstance(underlying, _CountingBytesIO)
    # Stopped well short of the full 3x body -- proves the cap fired
    # mid-stream instead of after buffering everything.
    assert underlying.bytes_read < len(oversized)


async def test_upload_within_cap_is_read_fully(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    within_cap = b"y" * 1024
    upload = _make_upload(within_cap)

    contents = await _authorize_and_read(upload, "hla_typing_report", settings.ocr_service_api_key)

    assert contents == within_cap


async def test_wrong_api_key_is_rejected_before_any_read(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    upload = _make_upload(b"irrelevant")

    with pytest.raises(HTTPException) as exc_info:
        await _authorize_and_read(upload, "hla_typing_report", "wrong-key")

    assert exc_info.value.status_code == 401
    assert upload.file.bytes_read == 0

# app/tests/unit/test_ocr_client.py
"""Confirms ocr_client streams the spooled file straight off disk instead
of reading it into a bytes object first — the whole point of the Part G
bounded-memory pass (a decoded phone photo is roughly 10x its JPEG size in
ocr-service's PIL step; holding the raw bytes here too, on top of that,
is exactly what spooling was meant to avoid). Guards against a future
refactor quietly reintroducing `upload.path.read_bytes()`, which would put
the full image back in RAM right before the point of transfer.

httpx.AsyncClient.post/.stream are monkeypatched directly rather than
mocked at the transport layer (respx etc.) — the whole point here is to
inspect exactly what object ocr_client hands to `files={"file": (...)}`,
which a transport-level mock would only see already-serialized.
"""
import httpx

from app.services.ocr_client import call_ocr_service, call_ocr_service_stream
from app.services.ocr_spool_service import SpooledUpload


def _spooled_upload(tmp_path, content: bytes) -> SpooledUpload:
    path = tmp_path / "hla_typing_report.jpg"
    path.write_bytes(content)
    return SpooledUpload(path=path, filename="hla_typing_report.jpg", content_type="image/jpeg")


async def test_call_ocr_service_uploads_an_open_file_handle_not_bytes(tmp_path, monkeypatch):
    upload = _spooled_upload(tmp_path, b"fake-image-bytes")
    captured = {}

    async def _fake_post(self, url, *, headers, data, files):
        filename, fh, content_type = files["file"]
        captured["filename"] = filename
        captured["content_type"] = content_type
        captured["is_bytes"] = isinstance(fh, (bytes, bytearray))
        captured["has_read"] = hasattr(fh, "read")
        captured["was_open"] = not fh.closed
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"structured": {}}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    result = await call_ocr_service(upload, "hla_typing_report")

    assert result == {"structured": {}}
    assert captured["filename"] == "hla_typing_report.jpg"
    assert captured["content_type"] == "image/jpeg"
    assert captured["is_bytes"] is False
    assert captured["has_read"] is True
    assert captured["was_open"] is True


async def test_call_ocr_service_stream_keeps_handle_open_for_whole_response(tmp_path, monkeypatch):
    upload = _spooled_upload(tmp_path, b"fake-image-bytes")
    captured = {}

    class _FakeStreamResponse:
        def __init__(self, fh):
            self._fh = fh

        def raise_for_status(self):
            pass

        async def aiter_text(self):
            # The handle must still be open while the body is actually
            # being consumed -- that's the entire point of wrapping the
            # `with` around the whole streamed response, not just the
            # call that creates it.
            assert self._fh.closed is False
            yield '{"type": "result", "document_type": "bead_specificity", "structured": {}}\n'

    class _FakeStreamContextManager:
        def __init__(self, fh):
            self._fh = fh

        async def __aenter__(self):
            return _FakeStreamResponse(self._fh)

        async def __aexit__(self, *exc_info):
            return False

    def _fake_stream(self, method, url, *, headers, data, files):
        filename, fh, content_type = files["file"]
        captured["fh"] = fh
        return _FakeStreamContextManager(fh)

    monkeypatch.setattr(httpx.AsyncClient, "stream", _fake_stream)

    events = [event async for event in call_ocr_service_stream(upload, "bead_specificity")]

    assert events == [
        {"type": "result", "document_type": "bead_specificity", "structured": {}}
    ]
    # Closed now that the whole streamed response has been fully consumed.
    assert captured["fh"].closed is True

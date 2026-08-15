# app/tests/unit/test_route_concurrency.py
#
# Part H fix coverage: routes.py's handlers used to call orient_image
# (PIL decode + EXIF transpose) and make_row_band_tiles (8 crops + 8 PNG
# encodes) synchronously inside `async def` request handlers, with no
# asyncio.to_thread offload -- during a decode this service couldn't
# accept a new request or even answer /health. Separately, the only
# concurrency bound (CONCURRENT_TILE_LIMIT's semaphore) was created INSIDE
# extract_bead_specificity_stream, so it was per-request: N concurrent
# requests got N independent semaphores of 1, i.e. N tiles in flight at
# once instead of 1.
#
# The offload test below is deliberately NOT "start a slow /extract, race
# a /health request against it, hope it observes the block" -- a real
# attempt at that (timing-based, health request created concurrently and
# raced with a wait_for timeout) turned out to pass EVEN WITH the
# to_thread fix reverted, because plain ASGI request handling has enough
# incidental await points before reaching orient_image (reading the
# multipart body, etc.) that the health check often sneaks in during one
# of those, not because the loop was actually free during the blocking
# call. Confirmed by deliberately reverting the fix and re-running that
# version of this test: it still passed, i.e. it was a false negative.
# Asserting which THREAD the decode function actually ran on is what
# to_thread's fix concretely guarantees, and is deterministic rather than
# a scheduling race.
import asyncio
import threading

from httpx import ASGITransport, AsyncClient

from app.api import routes
from app.core.config import settings
from app.extraction import llm_extract
from app.main import app

AUTH_HEADERS = {"X-Internal-Api-Key": settings.ocr_service_api_key}


def _fake_upload_file(name: str, content: bytes = b"fake-bytes"):
    return (name, content, "image/jpeg")


async def test_pil_decode_runs_off_the_event_loop_thread(monkeypatch):
    main_thread = threading.current_thread()
    decode_thread = {}

    def _capture_thread(image_bytes: bytes) -> bytes:
        decode_thread["thread"] = threading.current_thread()
        return image_bytes

    async def _fake_chat_json(*args, **kwargs):
        return {"patient_details": {}, "donor_details": {}, "patient_hla": [], "donor_hla": []}

    monkeypatch.setattr(llm_extract, "orient_image", _capture_thread)
    monkeypatch.setattr(llm_extract, "chat_json", _fake_chat_json)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/extract",
            data={"document_type": "hla_typing_report"},
            files={"file": _fake_upload_file("report.jpg")},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    # This is what asyncio.to_thread actually buys: the decode ran on a
    # worker thread, not the request-handling (event loop) thread, so a
    # real multi-minute decode can't block that loop from doing anything
    # else -- serving /health included.
    assert decode_thread["thread"] is not main_thread


async def test_concurrent_extract_requests_serialize_through_the_semaphore(monkeypatch):
    active = 0
    max_active = 0

    async def _fake_extract_hla_typing(image_bytes: bytes) -> dict:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.2)
        active -= 1
        return {"patient_details": {}, "donor_details": {}, "patient_hla": [], "donor_hla": []}

    # Patched on the `routes` module, not `llm_extract` -- `_run_extraction`
    # calls the name it imported (`from app.extraction.llm_extract import
    # extract_hla_typing`), so that's the reference that has to change for
    # the fake to actually be hit.
    monkeypatch.setattr(routes, "extract_hla_typing", _fake_extract_hla_typing)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(
            client.post(
                "/extract",
                data={"document_type": "hla_typing_report"},
                files={"file": _fake_upload_file("a.jpg")},
                headers=AUTH_HEADERS,
            ),
            client.post(
                "/extract",
                data={"document_type": "hla_typing_report"},
                files={"file": _fake_upload_file("b.jpg")},
                headers=AUTH_HEADERS,
            ),
        )

    assert all(r.status_code == 200 for r in responses)
    # The whole point: never more than one extraction active at once, even
    # though both requests were in flight concurrently. Unlike the offload
    # test above, this one's fake uses a genuine asyncio.sleep (not a
    # blocking call), so both requests' coroutines genuinely interleave on
    # the event loop -- what's actually gating them from running
    # simultaneously is the module-level semaphore, not scheduling luck.
    assert max_active == 1

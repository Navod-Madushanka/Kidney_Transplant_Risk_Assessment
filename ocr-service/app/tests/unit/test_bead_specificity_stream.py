# app/tests/unit/test_bead_specificity_stream.py
#
# Covers extract_bead_specificity_stream's progress-event contract (the
# per-tile percentage that feeds kidney-backend's ProgressEvent, in turn
# feeding the wizard's per-document extraction percentage) against a
# mocked Ollama HTTP layer (respx patches httpx.AsyncClient, no real
# network/Ollama needed) — same approach as test_chat_json_client.py.
import io

import httpx
import respx
from PIL import Image

from app.core.config import settings
from app.extraction.llm_extract import extract_bead_specificity, extract_bead_specificity_stream
from app.extraction.tiling import DEFAULT_NUM_TILES

CHAT_URL = f"{settings.ollama_base_url}/api/chat"


def _synthetic_page_bytes() -> bytes:
    # A real bead specificity chart is a tall, narrow table — exact
    # pixels don't matter here since Ollama itself is mocked, only that
    # make_row_band_tiles can crop it into DEFAULT_NUM_TILES row bands.
    img = Image.new("RGB", (200, 1600), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _ollama_response(content: str) -> dict:
    return {"message": {"role": "assistant", "content": content}, "done_reason": "stop"}


@respx.mock
async def test_stream_emits_progress_from_zero_through_every_tile():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_ollama_response('{"bead_specificity": []}'))
    )

    events = [event async for event in extract_bead_specificity_stream(_synthetic_page_bytes())]
    progress_events = [e for e in events if e["type"] == "progress"]

    assert [e["completed"] for e in progress_events] == list(range(DEFAULT_NUM_TILES + 1))
    assert all(e["total"] == DEFAULT_NUM_TILES for e in progress_events)
    # Exactly one result, and it comes last.
    assert [e["type"] for e in events].count("result") == 1
    assert events[-1]["type"] == "result"


@respx.mock
async def test_stream_result_merges_rows_from_every_tile():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=_ollama_response('{"bead_specificity": [{"antigen": "A23", "mfi": 490.5}]}')
        )
    )

    events = [event async for event in extract_bead_specificity_stream(_synthetic_page_bytes())]
    result = events[-1]

    # Every tile returned the same row (dedupe collapses the overlap-driven
    # duplicates, same as a real page's overlapping tiles would).
    assert result["structured"]["bead_specificity"] == [{"antigen": "A23", "mfi": 490.5}]
    assert result["structured"]["warning"] == "ai_extracted_verify_against_source_image"


@respx.mock
async def test_stream_records_failed_tile_count_in_warning_without_stopping():
    # One tile returning invalid JSON (never valid, even after chat_json's
    # own retry) must not take down the rest of the page -- it's counted
    # in the warning instead, matching extract_bead_specificity's
    # pre-streaming behavior.
    call_count = 0

    def _side_effect(request):
        nonlocal call_count
        call_count += 1
        # chat_json retries once per tile on invalid JSON -- fail every
        # attempt for the very first tile's two calls, succeed for the rest.
        if call_count <= 2:
            return httpx.Response(200, json=_ollama_response("not json"))
        return httpx.Response(
            200, json=_ollama_response('{"bead_specificity": [{"antigen": "A23", "mfi": 490.5}]}')
        )

    respx.post(CHAT_URL).mock(side_effect=_side_effect)

    events = [event async for event in extract_bead_specificity_stream(_synthetic_page_bytes())]
    result = events[-1]

    assert result["structured"]["warning"] == (
        f"1_of_{DEFAULT_NUM_TILES}_tiles_failed_ai_extracted_verify_against_source_image"
    )


@respx.mock
async def test_non_streaming_wrapper_still_returns_final_structured_only():
    # extract_bead_specificity (used by the non-stream /extract-batch path)
    # must keep returning exactly the structured dict it always did, with
    # no progress events leaking into its return value.
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_ollama_response('{"bead_specificity": []}'))
    )

    structured = await extract_bead_specificity(_synthetic_page_bytes())

    assert structured == {"bead_specificity": [], "warning": "ai_extracted_verify_against_source_image"}

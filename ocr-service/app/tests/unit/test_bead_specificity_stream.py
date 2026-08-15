# app/tests/unit/test_bead_specificity_stream.py
#
# Covers extract_bead_specificity_stream's progress-event contract (the
# per-tile percentage that feeds kidney-backend's ProgressEvent, in turn
# feeding the wizard's per-document extraction percentage) and its
# reconciled-row/structured-warnings result shape, against a mocked Ollama
# HTTP layer (respx patches httpx.AsyncClient, no real network/Ollama
# needed) — same approach as test_chat_json_client.py.
import io
import json

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


def _sequential_side_effect(bodies: list[str]):
    """respx side_effect that returns `bodies[i]` on the i-th call --
    CONCURRENT_TILE_LIMIT=1 means tiles run strictly sequentially, so call
    order matches tile order 1:1."""
    calls = {"count": 0}

    def _side_effect(request):
        index = calls["count"]
        calls["count"] += 1
        return httpx.Response(200, json=_ollama_response(bodies[index]))

    return _side_effect


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
async def test_stream_result_reconciles_identical_rows_from_every_tile():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json=_ollama_response(
                '{"bead_specificity": [{"bead": "011", "antigen": "A23", "mfi": 490.5}]}'
            ),
        )
    )

    events = [event async for event in extract_bead_specificity_stream(_synthetic_page_bytes())]
    result = events[-1]

    # Every tile returned the same bead -- reconciliation merges the
    # overlap-driven re-reads into one row, same as a real page's
    # overlapping tiles would.
    assert result["structured"]["bead_specificity"] == [
        {"bead": "011", "antigen": "A23", "mfi": 490.5, "conflict": None}
    ]
    codes = {w["code"] for w in result["structured"]["warnings"]}
    assert codes == {"verify_against_source"}


@respx.mock
async def test_stream_records_failed_tile_count_in_warnings_without_stopping():
    # One tile returning invalid JSON (never valid, even after chat_json's
    # own retry) must not take down the rest of the page -- it's counted
    # in the structured warnings instead, matching extract_bead_specificity's
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
            200,
            json=_ollama_response(
                '{"bead_specificity": [{"bead": "011", "antigen": "A23", "mfi": 490.5}]}'
            ),
        )

    respx.post(CHAT_URL).mock(side_effect=_side_effect)

    events = [event async for event in extract_bead_specificity_stream(_synthetic_page_bytes())]
    result = events[-1]

    tiles_failed = next(
        w for w in result["structured"]["warnings"] if w["code"] == "tiles_failed"
    )
    assert tiles_failed["detail"] == f"1 of {DEFAULT_NUM_TILES} tiles failed to extract"


@respx.mock
async def test_stream_reconciles_a_mixed_page_with_conflict_gap_and_degenerate_tile():
    # A realistic mixed page in one pass: bead 002 disagrees across two
    # tiles (conflict), bead 003 is never seen (gap), and one tile
    # degenerates into repeating a row (the exact hallucination tiling
    # exists to fight -- see llm_extract.py's CONCURRENT_TILE_LIMIT
    # comment). DEFAULT_NUM_TILES=8, one body per tile in submission order.
    degenerate_body = json.dumps(
        {"bead_specificity": [{"bead": None, "antigen": "ZZ", "mfi": 999.0} for _ in range(40)]}
    )
    bodies = [
        '{"bead_specificity": [{"bead": "001", "antigen": "A1", "mfi": 100.0}]}',
        '{"bead_specificity": [{"bead": "002", "antigen": "A2", "mfi": 200.0}]}',
        '{"bead_specificity": [{"bead": "002", "antigen": "A2", "mfi": 400.0}]}',
        '{"bead_specificity": [{"bead": "004", "antigen": "A4", "mfi": 40.0}]}',
        degenerate_body,
        '{"bead_specificity": [{"bead": "006", "antigen": "A6", "mfi": 60.0}]}',
        '{"bead_specificity": [{"bead": "007", "antigen": "A7", "mfi": 70.0}]}',
        '{"bead_specificity": [{"bead": "008", "antigen": "A8", "mfi": 71.0}]}',
    ]
    assert len(bodies) == DEFAULT_NUM_TILES
    respx.post(CHAT_URL).mock(side_effect=_sequential_side_effect(bodies))

    events = [event async for event in extract_bead_specificity_stream(_synthetic_page_bytes())]
    structured = events[-1]["structured"]
    rows = structured["bead_specificity"]
    warnings = structured["warnings"]

    conflict_row = next(row for row in rows if row["bead"] == "002")
    assert conflict_row["conflict"] == [200.0, 400.0]
    assert conflict_row["mfi"] == 400.0  # highest candidate, never silently first-wins

    codes = {w["code"] for w in warnings}
    assert codes == {"verify_against_source", "conflict", "gap", "degenerate_tile"}

    # Both 003 and 005 are absent from the observed 001..008 range.
    gap_warning = next(w for w in warnings if w["code"] == "gap")
    assert gap_warning["bead_ids"] == ["003", "005"]

    conflict_warning = next(w for w in warnings if w["code"] == "conflict")
    assert conflict_warning["bead_ids"] == ["002"]


@respx.mock
async def test_non_streaming_wrapper_still_returns_final_structured_only():
    # extract_bead_specificity (used by direct /extract callers) must keep
    # returning exactly the structured dict extract_bead_specificity_stream's
    # final event carries, with no progress events leaking into its return
    # value.
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_ollama_response('{"bead_specificity": []}'))
    )

    structured = await extract_bead_specificity(_synthetic_page_bytes())

    assert structured["bead_specificity"] == []
    assert {w["code"] for w in structured["warnings"]} == {"verify_against_source"}

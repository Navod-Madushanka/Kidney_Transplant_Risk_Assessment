# app/tests/unit/test_chat_json_client.py
#
# Covers app/llm/client.py's chat_json/_post against a mocked Ollama HTTP
# layer (respx patches httpx.AsyncClient, no real network or Ollama
# needed). This is the failure-mode contract Phase 2/3 designed carefully
# -- hard failures must raise LLMExtractionError with a clear, specific
# message, never fall back to a silent/partial result. See client.py's
# module docstring for why that matters here (clinical lab data).
import httpx
import pytest
import respx

from app.llm.client import LLMExtractionError, chat_json

BASE_URL = "http://fake-ollama:11434"
CHAT_URL = f"{BASE_URL}/api/chat"


def _ollama_response(content: str, thinking: str | None = None, done_reason: str = "stop") -> dict:
    return {
        "message": {"role": "assistant", "content": content, "thinking": thinking},
        "done_reason": done_reason,
    }


@respx.mock
async def test_chat_json_success_first_try():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_ollama_response('{"a": 1}'))
    )
    result = await chat_json("fake-model", BASE_URL, "prompt", "base64img", label="test")
    assert result == {"a": 1}
    assert route.call_count == 1


@respx.mock
async def test_chat_json_retries_once_on_invalid_json_then_succeeds():
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_ollama_response("not json at all")),
            httpx.Response(200, json=_ollama_response('{"a": 1}')),
        ]
    )
    result = await chat_json("fake-model", BASE_URL, "prompt", "base64img", label="test")
    assert result == {"a": 1}
    assert route.call_count == 2


@respx.mock
async def test_chat_json_raises_if_both_attempts_invalid_json():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_ollama_response("still not json"))
    )
    with pytest.raises(LLMExtractionError, match="never returned valid JSON"):
        await chat_json("fake-model", BASE_URL, "prompt", "base64img", label="test-label")
    assert route.call_count == 2


@respx.mock
async def test_chat_json_raises_clear_error_when_model_not_found():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            404, json={"error": "model 'qwen3-vl:4b' not found, try pulling it first"}
        )
    )
    with pytest.raises(LLMExtractionError, match="not found"):
        await chat_json("qwen3-vl:4b", BASE_URL, "prompt", "base64img", label="test")


@respx.mock
async def test_chat_json_model_not_found_not_confused_with_nothink_suffix():
    # Regression test for a real bug fixed 2026-08-01: checking for the
    # substring "think" anywhere in the error body was a false positive
    # for any "-nothink"-suffixed model name -- a genuine "model not
    # found" error would be misread as "Ollama rejected the think field"
    # and retried pointlessly forever. Must still raise the clear
    # model-not-found message, not a generic one.
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(404, json={"error": "model 'qwen3-vl:4b-nothink' not found"})
    )
    with pytest.raises(LLMExtractionError, match="not found"):
        await chat_json("qwen3-vl:4b-nothink", BASE_URL, "prompt", "base64img", label="test")


@respx.mock
async def test_chat_json_raises_on_generic_http_error():
    respx.post(CHAT_URL).mock(return_value=httpx.Response(500, json={"error": "internal error"}))
    with pytest.raises(LLMExtractionError, match="HTTP 500"):
        await chat_json("fake-model", BASE_URL, "prompt", "base64img", label="test")


@respx.mock
async def test_chat_json_raises_on_timeout():
    respx.post(CHAT_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(LLMExtractionError, match="didn't finish within"):
        await chat_json("fake-model", BASE_URL, "prompt", "base64img", label="hla_typing_report")


@respx.mock
async def test_chat_json_raises_on_empty_content():
    # Should only happen if the -nothink Modelfile variant isn't actually
    # built (see docker/ollama-entrypoint.sh) -- content comes back empty
    # while the model reasoned in the hidden "thinking" channel instead.
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=_ollama_response("", thinking="reasoning happened here")
        )
    )
    with pytest.raises(LLMExtractionError, match="empty content"):
        await chat_json("fake-model", BASE_URL, "prompt", "base64img", label="test")


@respx.mock
async def test_chat_json_raises_on_connection_error():
    respx.post(CHAT_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(LLMExtractionError, match="Couldn't reach Ollama"):
        await chat_json("fake-model", BASE_URL, "prompt", "base64img", label="test")


@respx.mock
async def test_chat_json_strips_markdown_fence_without_retry():
    # If the model wraps valid JSON in a ```json fence despite
    # JSON_ONLY_INSTRUCTION, that should parse on the first try -- no
    # wasted retry round-trip.
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_ollama_response('```json\n{"a": 1}\n```'))
    )
    result = await chat_json("fake-model", BASE_URL, "prompt", "base64img", label="test")
    assert result == {"a": 1}
    assert route.call_count == 1

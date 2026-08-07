# app/llm/client.py
"""
Thin async client for Ollama's /api/chat endpoint. Replaces
app/ocr/engine.py's PaddleOCR wrapper as of the OCR -> local vision-LLM
migration (see claude/ocr-to-local-llm-migration-plan.md in the project).

Ported from llm-migration-spike/run_eval.py's call_ollama/_post_ollama,
adapted to async httpx (matching kidney-backend's ocr_client.py convention)
instead of the spike's sync urllib, and to raise on hard failures (network
unreachable, model missing, never-valid JSON) instead of printing and
falling back — routes.py turns LLMExtractionError into the same HTTP error
codes kidney-backend's ocr_client.py already knows how to handle
(httpx.HTTPStatusError -> 502, httpx.TimeoutException -> 504, etc.), so
hard failures surface loudly instead of silently returning an empty or
unreliable result. This matters more here than in most services: this is
clinical lab data, and the migration plan's non-negotiable safety-net
principle is "OCR fails loud, an LLM can fail quiet" — this client is
written to fail loud too.
"""
import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 180.0  # Widened 2026-08-01 after a real run: the FIRST
                                   # request after a container (re)start has to pay a
                                   # one-time cost loading the model into memory
                                   # (observed ~88s on CPU) on top of actual
                                   # generation time, which blew past the original
                                   # 120s budget with little margin left for
                                   # generation. That load cost isn't paid again for
                                   # OLLAMA_KEEP_ALIVE's duration (5 min default), so
                                   # this padding mostly matters for the first call.
                                   # Also see docker-compose.override.yml — running
                                   # without GPU passthrough is the bigger factor in
                                   # slow inference than this timeout value.

# CONFIRMED ROOT CAUSE (verified 2026-07-31 against ollama/ollama#13353,
# #14798, #14645): "think": false in the request payload is silently
# ignored by the qwen3-vl family in Ollama, and so is the documented
# "/no_think" prompt suffix — the model always reasons in a hidden channel
# and message.content comes back empty. The real fix ships at the model
# level: docker/ollama-entrypoint.sh builds a Modelfile variant with
# RENDERER/PARSER overridden to qwen3-vl-instruct, which bypasses the
# broken per-request toggle entirely. This suffix and the "think": false
# field below are kept as harmless no-ops in case a future Ollama version
# starts honoring them — don't rely on either alone.
NO_THINK_SUFFIX = "\n\n/no_think"


class LLMExtractionError(RuntimeError):
    """Raised for hard failures — Ollama unreachable, model missing, empty
    content, or invalid JSON even after one retry. Should always be caught
    at the routes.py boundary and turned into a real HTTP error; never
    swallowed into a silently-empty structured result."""


async def chat_json(
    model: str,
    base_url: str,
    prompt: str,
    image_b64: str,
    *,
    label: str = "",
    num_ctx: int = 8192,
    num_predict: int = 2048,
) -> dict:
    """Calls Ollama's chat API with format='json', parses the response,
    retries once with a stricter follow-up instruction if the first
    response doesn't parse as JSON. Raises LLMExtractionError on hard
    failure.

    num_ctx/num_predict defaults lowered 2026-08-01 after a real run on the
    dev RTX 2060 (6GB VRAM, inside Docker) showed 16384 context forced
    Ollama to split the model 24/37 layers GPU/CPU (not enough VRAM for the
    full model + that much KV cache), dropping generation to ~8 tokens/sec
    — a full HLA response never finished inside the request timeout as a
    result. The full HLA prompt (image + text) only used 2,780 tokens, so
    8192 leaves comfortable headroom while roughly halving the KV cache's
    memory footprint, which should let more (plausibly all) layers fit on
    GPU. Bead specificity's per-tile calls already passed their own smaller
    values explicitly; this only changes the HLA/crossmatch single-shot
    default. If this still isn't enough headroom on a given machine, that's
    a real signal worth measuring rather than just pushing the timeout out
    further — see the docstring on REQUEST_TIMEOUT_SECONDS."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt + NO_THINK_SUFFIX, "images": [image_b64]}],
        "format": "json",
        "stream": False,
        "think": False,
        "keep_alive": -1,  # never unload between calls — matches OLLAMA_KEEP_ALIVE=-1
                            # on the container (docker-compose.yml); belt-and-suspenders
                            # for the case this client ever talks to an untuned instance.
        "options": {
            "temperature": 0,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "repeat_penalty": 1.1,  # Ollama's default. Phase 1 tried raising this to
                                     # 1.3 to fight bead-specificity repetition-loop
                                     # hallucination and it backfired — it also
                                     # penalizes the legitimate repeating scaffolding
                                     # of a JSON array (same {"antigen":...,"mfi":...}
                                     # shape once per row), causing premature
                                     # truncation. Leave at default.
        },
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        raw_text = await _post(client, base_url, payload, label)
        parsed = _try_parse_json(raw_text)
        if parsed is not None:
            return parsed

        payload["messages"].append({"role": "assistant", "content": raw_text})
        payload["messages"].append({
            "role": "user",
            "content": "That wasn't valid JSON. Respond again with ONLY the JSON object, nothing else." + NO_THINK_SUFFIX,
        })
        raw_text = await _post(client, base_url, payload, label)
        parsed = _try_parse_json(raw_text)
        if parsed is None:
            raise LLMExtractionError(f"Model never returned valid JSON for {label}.")
        return parsed


async def _post(client: httpx.AsyncClient, base_url: str, payload: dict, label: str) -> str:
    try:
        response = await client.post(f"{base_url}/api/chat", json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        error_body = e.response.text
        # BUG FIXED 2026-08-01 (found via llm-migration-spike/run_eval.py):
        # checking for the substring "think" anywhere in the error body is a
        # false positive for any "-nothink"-suffixed model name — a genuine
        # "model 'qwen3-vl:4b-nothink' not found" error would be misread as
        # "Ollama rejected the think field" and retried pointlessly forever.
        # Check "model ... not found" first and specifically.
        if "not found" in error_body.lower() and "model" in error_body.lower():
            raise LLMExtractionError(
                f"Ollama model '{payload.get('model')}' not found for {label}: {error_body.strip()} "
                f"— has docker/ollama-entrypoint.sh finished provisioning it yet?"
            ) from e
        raise LLMExtractionError(f"Ollama returned HTTP {e.response.status_code} for {label}: {error_body}") from e
    except httpx.TimeoutException as e:
        raise LLMExtractionError(
            f"Ollama request for {label} didn't finish within {REQUEST_TIMEOUT_SECONDS}s. "
            f"Confirmed 2026-08-01 this can fire while the model is generating perfectly "
            f"normally, just too slowly to finish in time (e.g. VRAM too small to fully "
            f"offload the model to GPU) — it isn't necessarily a repetition-loop hang. "
            f"Check the ollama container's logs for 'tg = N t/s' lines to tell the two "
            f"apart: steady non-trivial throughput means it's just slow, near-zero or "
            f"wildly fluctuating means it's genuinely stuck."
        ) from e
    except httpx.HTTPError as e:
        raise LLMExtractionError(f"Couldn't reach Ollama for {label}: {e}") from e

    body = response.json()
    _log_timing(label, body)
    message = body.get("message", {})
    content = message.get("content", "")
    if not content:
        # Should only happen if the -nothink Modelfile variant isn't
        # actually in place (see docker/ollama-entrypoint.sh). The Phase 1
        # spike had a "salvage a JSON object out of the thinking field"
        # fallback here, but that was demonstrated unreliable — identical
        # temperature=0 runs against the same image swung between 15/15 and
        # 8/15 correct fields (see the migration plan's Phase 1 Results).
        # This is clinical lab data: fail loud here instead of silently
        # returning a possibly-incomplete answer.
        raise LLMExtractionError(
            f"Ollama returned empty content for {label} "
            f"(thinking_present={bool(message.get('thinking'))}, "
            f"done_reason={body.get('done_reason')!r}) — the -nothink model "
            f"variant may not be built correctly."
        )
    return content


# Phase 1 speed pass (2026-08-04, see claude/ocr-pipeline-optimization-plan.md
# 0.2): Ollama returns these token/duration fields on every /api/chat
# response for free. Logging them is what turns "does the speed pass help"
# from a stopwatch guess into a real before/after number — without this,
# there's no way to tell a GPU-resident 50 tok/s run from a CPU-offloaded
# 8 tok/s one after the fact.
def _log_timing(label: str, body: dict) -> None:
    prompt_eval_count = body.get("prompt_eval_count")
    eval_count = body.get("eval_count")
    eval_duration = body.get("eval_duration")  # nanoseconds
    load_duration = body.get("load_duration")  # nanoseconds

    decode_tok_s = None
    if eval_count and eval_duration:
        decode_tok_s = eval_count / (eval_duration / 1e9)

    logger.info(
        "ollama_timing label=%s prompt_eval_count=%s eval_count=%s "
        "eval_duration_s=%s load_duration_s=%s decode_tok_s=%s",
        label,
        prompt_eval_count,
        eval_count,
        f"{eval_duration / 1e9:.2f}" if eval_duration else None,
        f"{load_duration / 1e9:.2f}" if load_duration else None,
        f"{decode_tok_s:.1f}" if decode_tok_s else None,
    )


def _try_parse_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: grab the outermost {...} span in case there's stray prose
    # around the JSON despite instructions.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None

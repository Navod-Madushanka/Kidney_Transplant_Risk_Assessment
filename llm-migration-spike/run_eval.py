#!/usr/bin/env python3
"""
run_eval.py — Phase 1 spike harness for the OCR -> local vision-LLM migration.

Calls a local Ollama model against the real sample documents and scores its
structured JSON output against the hand-verified ground truth fixtures in
fixtures/. This is throwaway/scratch code per the migration plan (see
claude/ocr-to-local-llm-migration-plan.md) — it does not touch ocr-service
at all. Its only job is to answer: "does this model clear the accuracy bar
before we build the real thing?"

Usage (PowerShell):
    python run_eval.py --model qwen3-vl:2b --images "C:\\path\\to\\your\\photos"

The --images folder must contain these four files (same names used
throughout this project's testing so far):
    sample.jpg               (HLA typing report)
    sample_simple.jpg         (crossmatch report)
    sample_mfi_page1.jpg      (bead specificity chart, page 1)
    sample_mfi_page2.jpg      (bead specificity chart, page 2)

Requires Ollama running locally (default http://localhost:11434) with the
chosen model already pulled (`ollama pull qwen3-vl:2b`), and Pillow
installed (`pip install pillow`) for the bead-specificity image tiling.
"""
import argparse
import base64
import io
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

from prompts import HLA_TYPING_PROMPT, CROSSMATCH_PROMPT, BEAD_SPECIFICITY_PROMPT

try:
    from PIL import Image
except ImportError:
    Image = None

SCRIPT_DIR = Path(__file__).parent
FIXTURES_DIR = SCRIPT_DIR / "fixtures"
RESULTS_DIR = SCRIPT_DIR / "results"

OLLAMA_URL = "http://localhost:11434/api/chat"
REQUEST_TIMEOUT_SECONDS = 600  # generous — CPU/first-load inference, or a model stuck
                                # repetition-looping toward num_predict, can be slow

# CONFIRMED ROOT CAUSE (2026-07-31): both "think": false and this /no_think
# suffix are silent no-ops against qwen3-vl in Ollama — a known, currently
# open upstream bug (ollama/ollama#13353, #14798): the qwen3-vl renderer
# never wires the per-request "think" toggle into actual generation, so the
# model always thinks, message.content always comes back empty, and (per a
# related bug, #14645) "format": "json" doesn't apply properly either while
# this is broken. The salvage-from-"thinking" fallback below exists because
# of this bug, but it's inherently unreliable — thinking text isn't
# guaranteed to contain the *complete* answer, which is why identical
# temperature=0 runs against the same image swung between 15/15 and 8/15 on
# the crossmatch doc. The real fix is NOT in this script: build a
# non-thinking model variant via a Modelfile that overrides RENDERER/PARSER
# to "qwen3-vl-instruct" (see README.md) and pass --model <that-variant>.
# Kept as a best-effort suffix in case a future Ollama version starts
# honoring it — should be a harmless no-op either way.
NO_THINK_SUFFIX = "\n\n/no_think"


def image_bytes_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def load_image_b64(path: Path) -> str:
    return image_bytes_to_b64(path.read_bytes())


def make_row_band_tiles(image_path: Path, num_tiles: int = 4, overlap_frac: float = 0.12) -> list[bytes]:
    """Splits the image into num_tiles horizontal bands (full width, with a
    bit of vertical overlap so a row straddling a cut line still appears
    whole in at least one tile), returned as PNG bytes. Used for the bead
    specificity chart — asking a 2B model to enumerate ~100 rows in one shot
    empirically collapsed into repetitive hallucination (see the migration
    plan's Phase 1 notes); smaller row-bands per call is the documented
    fallback in that same plan, just pulled forward once the single-shot
    attempt actually failed rather than waiting for Phase 2."""
    if Image is None:
        raise RuntimeError("Pillow is required for bead-specificity tiling — install with `pip install pillow`.")
    img = Image.open(image_path)
    w, h = img.size
    band_h = h / num_tiles
    overlap = band_h * overlap_frac
    tiles = []
    for i in range(num_tiles):
        top = max(0, i * band_h - overlap)
        bottom = min(h, (i + 1) * band_h + overlap)
        crop = img.crop((0, int(top), w, int(bottom)))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        tiles.append(buf.getvalue())
    return tiles


def call_ollama(
    model: str,
    prompt: str,
    image_b64: str,
    label: str,
    num_ctx: int = 16384,
    num_predict: int = 4096,
) -> dict:
    """Calls Ollama's chat API with format='json' to force valid JSON output,
    then parses the response. Retries once, with a stricter follow-up
    instruction, if the first response doesn't parse — models sometimes wrap
    JSON in prose or a code fence despite instructions.

    NOTE (2026-07-31): both "think": false and the "/no_think" prompt suffix
    were tested against qwen3-vl:2b and BOTH were silently ignored — every
    response still came back with a populated "thinking" field. Kept here
    as harmless no-ops in case a different model/Ollama version honors
    them, but don't assume either actually works without checking the
    [debug] output."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt + NO_THINK_SUFFIX, "images": [image_b64]}],
        "format": "json",
        "stream": False,
        "think": False,  # observed to be ignored by qwen3-vl:2b — see note above
        "options": {
            "temperature": 0,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "repeat_penalty": 1.1,  # Ollama's own default. A 2026-07-31 attempt to raise this to
                                     # 1.3 to fight the bead-specificity repetition loop backfired —
                                     # it also penalizes the legitimate repeating scaffolding of a
                                     # JSON array (the same {"antigen":...,"mfi":...} shape appears
                                     # once per row), which looks like why tiles started giving up
                                     # after 2-4 rows instead of the ~20+ actually on each band. The
                                     # repetition-loop problem is much more likely the broken
                                     # thinking/format interaction (ollama/ollama#14645) than a
                                     # sampling-parameter problem — fix that first (see README) before
                                     # reaching for repeat_penalty again.
        },
    }
    raw_text = _post_ollama(payload, label)
    parsed = _try_parse_json(raw_text)
    if parsed is not None:
        return parsed

    print(f"    [retry] first response wasn't valid JSON, retrying once for {label}...")
    payload["messages"].append({"role": "assistant", "content": raw_text})
    payload["messages"].append({
        "role": "user",
        "content": "That wasn't valid JSON. Respond again with ONLY the JSON object, nothing else." + NO_THINK_SUFFIX,
    })
    raw_text = _post_ollama(payload, label)
    parsed = _try_parse_json(raw_text)
    if parsed is None:
        raise ValueError(f"Model never returned valid JSON for {label}. Last raw response:\n{raw_text}")
    return parsed


def _post_ollama(payload: dict, label: str = "") -> str:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        # BUG FIXED 2026-08-01: the old check here was `"think" in
        # error_body.lower()`, which is a false positive for ANY model whose
        # *name* contains "think" — e.g. every "-nothink" variant this
        # project uses. A genuine "model 'qwen3-vl:4b-nothink' not found"
        # error was being misread as "Ollama rejected the think field",
        # triggering a pointless pop-and-retry that just failed again with
        # the same "not found" error, forever (once per call site, which is
        # why the terminal filled with dozens of identical [info] lines
        # instead of one clear error). Check for "model not found" FIRST and
        # specifically, and only treat it as a rejected-field issue if the
        # body actually says something like 'unknown field "think"'.
        if "not found" in error_body.lower() and "model" in error_body.lower():
            raise RuntimeError(
                f"Ollama says the model '{payload.get('model')}' doesn't exist for {label}: "
                f"{error_body.strip()}\n"
                f"    If this is a '-nothink' variant, you need to build it first — see README.md "
                f"step 5 (ollama show <model> --modelfile, add RENDERER/PARSER lines, then "
                f"ollama create <model>-nothink -f <that file>)."
            ) from e
        if "unknown field" in error_body.lower() and '"think"' in error_body:
            # Older Ollama build that doesn't understand the "think" field —
            # drop it and retry once rather than failing outright.
            print(f"    [info] Ollama rejected the 'think' option ({error_body.strip()}) — retrying without it.")
            payload.pop("think", None)
            return _post_ollama(payload, label)
        raise RuntimeError(f"Ollama returned HTTP {e.code} for {label}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Couldn't reach Ollama at {OLLAMA_URL} — is `ollama serve` running "
            f"and is the model pulled? ({e})"
        ) from e
    except TimeoutError as e:
        # A read-phase timeout (connection succeeded, response never finished)
        # raises a bare TimeoutError that urllib does NOT wrap in URLError —
        # needs its own handler or it crashes the whole script instead of
        # just failing this one call. Usually means the model is stuck
        # generating (e.g. a repetition loop) past REQUEST_TIMEOUT_SECONDS.
        raise RuntimeError(
            f"Ollama request for {label} timed out after {REQUEST_TIMEOUT_SECONDS}s — "
            f"the model may be stuck in a repetition loop rather than actually hanging."
        ) from e

    message = body.get("message", {})
    content = message.get("content", "")
    if not content:
        # Diagnostic dump — most likely causes: the model spent its whole
        # output budget on hidden "thinking" tokens (check message.get
        # ('thinking')), or done_reason == 'length' means num_predict/num_ctx
        # was still too small.
        print(f"    [debug] empty content from Ollama for {label}. "
              f"done_reason={body.get('done_reason')!r} "
              f"thinking_present={bool(message.get('thinking'))} "
              f"full_body_keys={list(body.keys())}")
        thinking = message.get("thinking", "")
        if thinking:
            print(f"    [debug] 'thinking' field had {len(thinking)} chars — "
                  f"attempting to salvage a JSON object from it as a fallback. "
                  f"If /no_think isn't being honored, results may still be unreliable.")
            return thinking
    return content


def _try_parse_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    # Strip a markdown code fence if the model added one despite instructions.
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: the text may be prose/reasoning with a JSON object embedded
    # in it (e.g. salvaged from a "thinking" field) — grab the outermost
    # {...} span and try that instead of giving up.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def compare_field(path: str, expected, actual, mismatches: list) -> bool:
    """Recursively compares expected vs actual, normalizing whitespace/case
    for strings. Appends (path, expected, actual) to mismatches on failure."""
    if isinstance(expected, dict):
        ok = True
        for key, exp_val in expected.items():
            act_val = actual.get(key) if isinstance(actual, dict) else None
            ok = compare_field(f"{path}.{key}", exp_val, act_val, mismatches) and ok
        return ok
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            mismatches.append((path, f"list of {len(expected)}", f"list of {len(actual) if isinstance(actual, list) else type(actual).__name__}"))
            return False
        ok = True
        for i, (exp_item, act_item) in enumerate(zip(expected, actual)):
            ok = compare_field(f"{path}[{i}]", exp_item, act_item, mismatches) and ok
        return ok
    if _norm(expected) != _norm(actual):
        mismatches.append((path, expected, actual))
        return False
    return True


def score_structured_doc(label: str, ground_truth: dict, predicted: dict) -> None:
    mismatches: list = []
    ok = compare_field(label, ground_truth, predicted, mismatches)
    total_leaf_fields = _count_leaves(ground_truth)
    failed = len(mismatches)
    passed = total_leaf_fields - failed
    print(f"\n=== {label}: {passed}/{total_leaf_fields} fields matched ===")
    if ok:
        print("    ALL FIELDS MATCHED.")
    else:
        for path, exp, act in mismatches:
            print(f"    MISMATCH {path}\n        expected: {exp!r}\n        actual:   {act!r}")


def _count_leaves(obj) -> int:
    if isinstance(obj, dict):
        return sum(_count_leaves(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_count_leaves(v) for v in obj)
    return 1


def score_bead_specificity(label: str, anchors: list, predicted_rows: list, tolerance_pct: float = 0.15) -> None:
    # Known simplification: when two anchors share the same antigen name
    # (e.g. two "A24" rows with different MFI), this doesn't prevent both
    # anchors from matching against the same single predicted row. Fine for
    # a quick spike signal; don't read too much into small anchor-count
    # differences for antigens with duplicate names.
    print(f"\n=== {label}: anchor spot-check ({len(anchors)} anchor rows — NOT the full table) ===")
    pred_by_antigen: dict[str, list] = {}
    for row in predicted_rows:
        pred_by_antigen.setdefault(_norm(row.get("antigen", "")), []).append(row.get("mfi"))

    matched = 0
    for anchor in anchors:
        antigen_key = _norm(anchor["antigen"])
        candidates = pred_by_antigen.get(antigen_key, [])
        if not candidates:
            print(f"    MISSING  antigen={anchor['antigen']!r} (expected mfi~{anchor['mfi']})")
            continue
        expected_mfi = anchor["mfi"]
        best = min(candidates, key=lambda v: abs((v or 0) - expected_mfi))
        # BUG FIXED 2026-07-31: "same side of the 1000 threshold" was being
        # applied as a blanket fallback regardless of magnitude — which
        # quietly counted a match for ANY two values both over 1000, even
        # 23706.91 vs 22566.73 (a genuinely wrong reading, not a borderline
        # call). That's meaningless for page 1's rows, which all sit tens of
        # thousands above the threshold. Restrict this leniency to values
        # actually near the boundary (a 3x band either side) — the only
        # place "which side of the line" is a legitimately softer bar than
        # "how close is the number."
        near_threshold = 300 <= expected_mfi <= 3000
        same_side_of_threshold = near_threshold and (best is not None) and ((best > 1000) == (expected_mfi > 1000))
        within_tolerance = (best is not None) and (abs(best - expected_mfi) <= tolerance_pct * max(expected_mfi, 1))
        if within_tolerance or same_side_of_threshold:
            matched += 1
            print(f"    OK       antigen={anchor['antigen']!r} expected~{expected_mfi} got={best}")
        else:
            print(f"    OFF      antigen={anchor['antigen']!r} expected~{expected_mfi} got={best}")

    print(f"    -> {matched}/{len(anchors)} anchors matched")
    print(f"    Model returned {len(predicted_rows)} total rows this page — "
          f"eyeball the full result in results/ against the actual chart yourself, "
          f"this anchor set is a sanity check, not a complete grade.")


def dedupe_rows(rows: list) -> list:
    """Drops exact-duplicate (antigen, mfi) pairs that show up twice because
    of tile overlap — keeps first occurrence order."""
    seen = set()
    out = []
    for row in rows:
        key = (_norm(row.get("antigen", "")), row.get("mfi"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def run_bead_specificity_tiled(model: str, image_path: Path, doc_key: str, num_tiles: int = 4) -> dict:
    print(f"\nRunning {model} on {image_path.name} in {num_tiles} row-band tiles "
          f"(single-shot on the full page failed — see migration plan notes)...")
    tiles = make_row_band_tiles(image_path, num_tiles=num_tiles)
    all_rows = []
    for i, tile_bytes in enumerate(tiles):
        label = f"{image_path.name} tile {i + 1}/{num_tiles}"
        print(f"    tile {i + 1}/{num_tiles} ...")
        try:
            # Smaller ctx/predict than the full-page HLA/crossmatch calls —
            # each tile only covers ~1/num_tiles of the table, so it doesn't
            # need room for 100 rows, and capping num_predict lower also
            # bounds how long a repetition-loop failure can run before
            # giving up rather than eating the full timeout.
            result = call_ollama(
                model, BEAD_SPECIFICITY_PROMPT, image_bytes_to_b64(tile_bytes), label,
                num_ctx=8192, num_predict=1536,
            )
        except (ValueError, RuntimeError) as e:
            # RuntimeError covers a request timeout (see _post_ollama) — one
            # stuck tile shouldn't take down the other three.
            print(f"    [warn] tile {i + 1} failed, skipping it: {e}")
            continue
        rows = result.get("bead_specificity", [])
        print(f"    tile {i + 1}/{num_tiles} -> {len(rows)} rows")
        all_rows.extend(rows)
    merged = {"bead_specificity": dedupe_rows(all_rows)}
    out_path = RESULTS_DIR / f"{doc_key}.json"
    out_path.write_text(json.dumps(merged, indent=2))
    print(f"    Merged raw output ({len(merged['bead_specificity'])} rows after dedupe) saved to {out_path}")
    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", default="qwen3-vl:2b-nothink",
        help="Ollama model name (default: qwen3-vl:2b-nothink — a plain 'qwen3-vl:2b' hits a "
             "known Ollama bug where thinking can't be disabled; see README.md to build the "
             "-nothink variant first)",
    )
    parser.add_argument("--images", required=True, help="Folder containing the four sample images")
    parser.add_argument("--bead-tiles", type=int, default=4, help="Row-band tiles for the bead specificity chart (default: 4)")
    args = parser.parse_args()

    image_dir = Path(args.images)
    RESULTS_DIR.mkdir(exist_ok=True)

    def load_fixture(name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text())

    def run_one(doc_key: str, image_name: str, prompt: str) -> dict:
        image_path = image_dir / image_name
        if not image_path.exists():
            print(f"!! Skipping {doc_key}: {image_path} not found")
            return {}
        print(f"\nRunning {args.model} on {image_name} ...")
        predicted = call_ollama(args.model, prompt, load_image_b64(image_path), image_name)
        out_path = RESULTS_DIR / f"{doc_key}.json"
        out_path.write_text(json.dumps(predicted, indent=2))
        print(f"    Raw output saved to {out_path}")
        return predicted

    hla_gt = load_fixture("hla_typing_ground_truth.json")
    hla_pred = run_one("hla_typing", "sample.jpg", HLA_TYPING_PROMPT)
    if hla_pred:
        score_structured_doc("HLA typing report", {k: v for k, v in hla_gt.items() if not k.startswith("_")}, hla_pred)

    xm_gt = load_fixture("crossmatch_ground_truth.json")
    xm_pred = run_one("crossmatch", "sample_simple.jpg", CROSSMATCH_PROMPT)
    if xm_pred:
        score_structured_doc("Crossmatch report", {k: v for k, v in xm_gt.items() if not k.startswith("_")}, xm_pred)

    bead_gt = load_fixture("bead_specificity_anchor.json")

    p1_path = image_dir / "sample_mfi_page1.jpg"
    if p1_path.exists():
        p1_pred = run_bead_specificity_tiled(args.model, p1_path, "bead_specificity_page1", args.bead_tiles)
        score_bead_specificity("Bead specificity — page 1", bead_gt["page1_anchors"], p1_pred.get("bead_specificity", []))
    else:
        print(f"!! Skipping bead_specificity_page1: {p1_path} not found")

    p2_path = image_dir / "sample_mfi_page2.jpg"
    if p2_path.exists():
        p2_pred = run_bead_specificity_tiled(args.model, p2_path, "bead_specificity_page2", args.bead_tiles)
        score_bead_specificity("Bead specificity — page 2", bead_gt["page2_anchors"], p2_pred.get("bead_specificity", []))
    else:
        print(f"!! Skipping bead_specificity_page2: {p2_path} not found")

    print("\nDone. Full raw model outputs are in results/ for manual review.")


if __name__ == "__main__":
    sys.exit(main())

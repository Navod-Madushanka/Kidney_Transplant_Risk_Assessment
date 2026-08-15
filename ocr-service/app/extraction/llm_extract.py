# app/extraction/llm_extract.py
"""
Generic LLM-backed extraction — replaces the four PaddleOCR column-
clustering modules (demographics.py, hla.py, mfi_extraction.py,
crossmatch_extraction.py) as of the OCR -> local vision-LLM migration. See
claude/ocr-to-local-llm-migration-plan.md in the project for the full
design rationale.

Each function here takes the raw image bytes for ONE uploaded document and
returns exactly the same `structured` shape the old modules produced — this
is the frozen external contract kidney-backend/kidney-frontend depend on.
Confirmed via grep against both repos (2026-08-01): neither consumes the
old `raw.texts`/`raw.boxes`/`raw.scores` OCR-box fields, and the frontend's
`OCR_LOW_CONFIDENCE_THRESHOLD` constant is dead code (never imported
anywhere) — so nothing here needs to fabricate a fake per-field confidence
score to replace PaddleOCR's per-box one. The frontend's only real signal
is the string-valued `structured["warning"]` field, which this module
reuses for every soft-failure case rather than inventing new response
fields.
"""
import asyncio
import base64
from dataclasses import replace
from typing import AsyncIterator

from app.core.config import settings
from app.extraction.bead_reconciliation import (
    BeadObservation,
    BeadReconciliationReport,
    coerce_bead_id,
    coerce_mfi,
    detect_degenerate_tiles,
    reconcile_bead_rows,
)
from app.extraction.preprocessing import orient_image
from app.extraction.tiling import make_row_band_tiles
from app.llm.client import LLMExtractionError, chat_json
from app.llm.prompts import BEAD_SPECIFICITY_PROMPT, CROSSMATCH_PROMPT, HLA_TYPING_PROMPT
from app.reference_data.hla_loci import HLA_LOCI

EMPTY_DETAILS = {"full_name": "", "nic_number": "", "date_of_birth": "", "blood_type": "", "hla_ref_no": ""}


def _b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


async def extract_hla_typing(image_bytes: bytes) -> dict:
    image_bytes = await asyncio.to_thread(orient_image, image_bytes)
    result = await chat_json(
        settings.ollama_model, settings.ollama_base_url, HLA_TYPING_PROMPT, _b64(image_bytes),
        label="hla_typing_report",
    )
    patient_details = {**EMPTY_DETAILS, **result.get("patient_details", {})}
    donor_details = {**EMPTY_DETAILS, **result.get("donor_details", {})}
    patient_hla, patient_warning = _validate_hla_rows(result.get("patient_hla", []))
    donor_hla, donor_warning = _validate_hla_rows(result.get("donor_hla", []))

    structured = {
        "patient_details": patient_details,
        "donor_details": donor_details,
        "patient_hla": patient_hla,
        "donor_hla": donor_hla,
    }
    warning = patient_warning or donor_warning
    if warning:
        structured["warning"] = warning
    return structured


def _validate_hla_rows(rows) -> tuple[list[dict], str | None]:
    """Drops any row whose locus isn't in the canonical HLA_LOCI set rather
    than trusting the model's spelling of it verbatim — repurposes
    hla_loci.py as a validator instead of a clustering target, per the
    migration plan's Phase 2 design."""
    valid, dropped = [], []
    for row in rows if isinstance(rows, list) else []:
        locus = row.get("locus", "") if isinstance(row, dict) else ""
        if locus in HLA_LOCI:
            valid.append({
                "locus": locus,
                "allele_1": str(row.get("allele_1", "")),
                "allele_2": str(row.get("allele_2", "")),
            })
        else:
            dropped.append(locus or "<missing>")
    warning = f"model_returned_unrecognized_locus:{','.join(dropped)}" if dropped else None
    return valid, warning


async def extract_crossmatch(image_bytes: bytes) -> dict:
    image_bytes = await asyncio.to_thread(orient_image, image_bytes)
    result = await chat_json(
        settings.ollama_model, settings.ollama_base_url, CROSSMATCH_PROMPT, _b64(image_bytes),
        label="crossmatch",
    )
    patient_details = {**EMPTY_DETAILS, **result.get("patient_details", {})}
    donor_details = {**EMPTY_DETAILS, **result.get("donor_details", {})}
    crossmatch = result.get("crossmatch", {}) if isinstance(result.get("crossmatch"), dict) else {}
    return {
        "patient_details": patient_details,
        "donor_details": donor_details,
        "crossmatch": {
            "t_cell_result": crossmatch.get("t_cell_result", ""),
            "b_cell_result": crossmatch.get("b_cell_result", ""),
            "interpretation": crossmatch.get("interpretation", ""),
            "remarks": crossmatch.get("remarks", ""),
            "test_date": crossmatch.get("test_date", ""),
        },
    }


# Per the migration plan's Phase 1 decision: bead specificity extraction
# accuracy didn't clear the same bar HLA typing/crossmatch did (Phase 1
# Results: 10/13 and 8/12 anchor rows matched, plus an occasional degraded
# tile), and doctor review was already mandatory for lab values regardless
# of accuracy. So this document type ALWAYS carries this warning, not just
# when something visibly went wrong — reusing the existing warning
# mechanism rather than adding a new response field.
BEAD_SPECIFICITY_ALWAYS_VERIFY_WARNING = "ai_extracted_verify_against_source_image"



# CHANGED 2026-08-01: this originally fired all 8 tiles via unbounded
# asyncio.gather, on the theory that concurrency was a free production win
# over the Phase 1 spike's sequential loop. A real run scored far worse
# than Phase 1 (10/13 -> 1/13, then 2/13 after an unrelated prompt revert
# ruled out prompt wording as the cause) with a much higher tile-failure
# count than Phase 1 ever saw (2/8, then 5/8 -- Phase 1's sequential spike
# rarely lost a tile at all). The ollama container's own startup logs
# report OLLAMA_NUM_PARALLEL=1 (never explicitly set by us -- this is
# Ollama's own default under this container's resource profile), meaning
# the server processes one request at a time regardless of how many we
# send at once. Sending all 8 concurrently doesn't get 8-way parallelism;
# it queues 7 of them. Each queued tile's REQUEST_TIMEOUT_SECONDS clock
# starts the moment httpx sends it, not when Ollama actually starts
# generating for it -- so a tile queued behind several ~15-40s-partial-GPU
# generations can burn most or all of its own timeout budget just waiting
# for a turn, before it ever produces a token. That lines up with the
# jump in failed-tile counts far better than "the prompt got worse" does,
# and it's a real mechanism, not a guess dressed up as one. Bounding
# client-side concurrency to CONCURRENT_TILE_LIMIT=1 matches what the
# server actually does today (serialize), so each tile gets its own full
# timeout budget starting from when it actually begins, like Phase 1's
# sequential spike did. If server-side parallelism is ever increased
# (e.g. more VRAM, explicit OLLAMA_NUM_PARALLEL), raise this to match --
# don't raise it speculatively without re-confirming the server's real
# parallelism first, or we're back to the same queuing problem.
#
# RESULT 2026-08-01: confirmed effective for what it targets -- a retest on
# sample_mfi_page1.jpg dropped failed tiles from 5/8 to 1/8, consistent
# with queuing-induced timeouts being real and now mostly eliminated. It
# did NOT fix overall anchor accuracy (still 2/13, same as the pre-fix
# revert run) -- the remaining problem lives inside individual tiles that
# DO return valid JSON in time, not in tiles timing out. Specifically, the
# tile covering the page's highest-MFI rows keeps collapsing multiple
# distinct antigens onto one duplicated value (six different labels all
# reported as the same 23706.91), and antigens that belong on page 2
# (DQ4, DP1) keep bleeding into page 1's output across multiple separate
# runs now -- a repeated pattern, not a one-off. This looks like a real,
# distinct failure mode (likely tied to that specific tile's row density
# and/or cross-page context bleed) rather than the queuing bug or the
# prompt wording. Treat this as still open; see
# claude/ocr-to-local-llm-migration-plan.md for the decision on how far to
# chase it before Phase 4.
CONCURRENT_TILE_LIMIT = 1


async def extract_bead_specificity_stream(
    image_bytes: bytes, band_edges: list[float] | None = None
) -> AsyncIterator[dict]:
    """Same extraction as extract_bead_specificity, but yields progress as
    each of the 8 row-band tiles finishes instead of only returning once
    the whole page is done. This is the one document type slow enough
    (1.5-3 min, 8 sequential vision-model calls) that a caller waiting on
    a single 0%->100% jump is a real UX problem — see routes.py's
    /extract/stream, which this feeds.

    Yields {"type": "progress", "completed": N, "total": len(tiles)} once
    per tile completion (starting with N=0 before any tile has run, so a
    caller knows the total immediately), then exactly one final
    {"type": "result", "structured": {...}} with the same shape
    extract_bead_specificity used to return directly.

    Tiles still run with the same CONCURRENT_TILE_LIMIT-bounded concurrency
    as before (see that constant's comment for why it's 1 today) — this
    only adds a queue so completions can be observed and yielded as they
    happen rather than all at once via asyncio.gather.

    band_edges -- the DSA clinical-severity band boundaries (see
    bead_reconciliation._clinical_band's docstring for why this is a
    parameter rather than a hardcoded constant here), forwarded to
    reconcile_bead_rows so a near-threshold tile disagreement is never
    waved off as noise. Optional: None degrades reconciliation to plain
    relative tolerance, no threshold-crossing rule.
    """
    # Orient (EXIF rotation only) BEFORE tiling — make_row_band_tiles crops
    # by raw pixel coordinates assuming the page is already upright. No
    # pixel-count cap here (see preprocessing.py's module docstring — that
    # part of the Phase 1 speed pass was reverted after it caused a real,
    # reproducible clinical-data misread in testing).
    #
    # Part H fix: both calls are synchronous PIL work (decode, EXIF
    # transpose, 8 crops + 8 PNG encodes) with no internal await, so called
    # directly inside this async def they'd block the whole event loop for
    # their duration -- during a decode this service couldn't accept a new
    # request or even answer /health. asyncio.to_thread hands them to a
    # worker thread so the loop stays responsive.
    image_bytes = await asyncio.to_thread(orient_image, image_bytes)
    tiles = await asyncio.to_thread(make_row_band_tiles, image_bytes)
    total = len(tiles)
    semaphore = asyncio.Semaphore(CONCURRENT_TILE_LIMIT)
    completions: asyncio.Queue = asyncio.Queue()

    async def _run_tile(index: int, tile_bytes: bytes) -> None:
        async with semaphore:
            try:
                result = await chat_json(
                    settings.ollama_model, settings.ollama_base_url, BEAD_SPECIFICITY_PROMPT, _b64(tile_bytes),
                    label=f"bead_specificity tile {index + 1}/{total}",
                    num_ctx=8192, num_predict=1536,
                )
                rows = result.get("bead_specificity", [])
                rows = rows if isinstance(rows, list) else []
            except LLMExtractionError:
                rows = None  # one bad tile shouldn't take down the whole page
        await completions.put((index, rows))

    tasks = [asyncio.create_task(_run_tile(i, t)) for i, t in enumerate(tiles)]

    yield {"type": "progress", "completed": 0, "total": total}

    tile_results: list = [None] * total
    for completed in range(1, total + 1):
        index, rows = await completions.get()
        tile_results[index] = rows
        yield {"type": "progress", "completed": completed, "total": total}

    await asyncio.gather(*tasks)  # already finished (each puts before returning); surfaces any stray exception

    failed_tiles = sum(1 for r in tile_results if r is None)

    observations: list[BeadObservation] = []
    for tile_index, rows in enumerate(tile_results):
        if not rows:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            antigen = str(row.get("antigen", "")).strip()
            if not antigen:
                continue
            observations.append(
                BeadObservation(
                    bead=coerce_bead_id(row.get("bead")),
                    antigen=antigen,
                    mfi=coerce_mfi(row.get("mfi")),
                    tile_index=tile_index,
                )
            )

    reconciled, report = reconcile_bead_rows(observations, num_tiles=total, band_edges=band_edges)
    report = replace(report, degenerate_tiles=detect_degenerate_tiles(tile_results))

    yield {
        "type": "result",
        "structured": {
            "bead_specificity": [
                {
                    "bead": row.bead,
                    "antigen": row.antigen,
                    "mfi": row.mfi,
                    "conflict": list(row.conflict) if row.conflict is not None else None,
                }
                for row in reconciled
            ],
            "warnings": _build_bead_warnings(report, failed_tiles, total),
        },
    }


async def extract_bead_specificity(image_bytes: bytes, band_edges: list[float] | None = None) -> dict:
    """Non-streaming callers (e.g. /extract for document_type=bead_specificity):
    drains extract_bead_specificity_stream and returns just the final
    structured result, discarding the intermediate progress events."""
    structured: dict = {}
    async for event in extract_bead_specificity_stream(image_bytes, band_edges=band_edges):
        if event["type"] == "result":
            structured = event["structured"]
    return structured


def _build_bead_warnings(
    report: BeadReconciliationReport, failed_tiles: int, total_tiles: int
) -> list[dict]:
    """Turns a BeadReconciliationReport into the structured warning list a
    caller renders. Per the migration plan's Phase 1 decision (accuracy on
    this document type never cleared the bar HLA typing/crossmatch did),
    the blanket "AI-extracted, verify" note always fires first — but it's
    one entry among several specific ones now, not the whole message. A
    warning that fires on every single extraction is, behaviourally, no
    warning at all; a specific "beads 044 and 051 disagreed" entry directs
    a doctor's attention to the ~3 rows that actually need a second look
    instead of asking for the whole ~100-row page to be re-read."""
    warnings = [
        {"code": "verify_against_source", "detail": BEAD_SPECIFICITY_ALWAYS_VERIFY_WARNING, "bead_ids": []}
    ]

    if failed_tiles:
        warnings.append(
            {
                "code": "tiles_failed",
                "detail": f"{failed_tiles} of {total_tiles} tiles failed to extract",
                "bead_ids": [],
            }
        )

    for tile_index in report.degenerate_tiles:
        warnings.append(
            {
                "code": "degenerate_tile",
                "detail": (
                    f"Tile {tile_index + 1} of {total_tiles} looks degenerate "
                    "(repeated or excessive rows) -- its data may be unreliable"
                ),
                "bead_ids": [],
            }
        )

    for conflict in report.conflicts:
        candidates = ", ".join("null" if c is None else str(c) for c in conflict.candidates)
        warnings.append(
            {
                "code": "conflict",
                "detail": (
                    f"Bead {conflict.key} had disagreeing MFI readings across tiles "
                    f"({candidates}) -- using the highest value, please verify"
                ),
                "bead_ids": [conflict.key],
            }
        )

    if report.gaps:
        warnings.append(
            {
                "code": "gap",
                "detail": f"Beads {', '.join(report.gaps)} appear missing from the observed range",
                "bead_ids": list(report.gaps),
            }
        )

    if report.unreadable_mfi:
        warnings.append(
            {
                "code": "unreadable_mfi",
                "detail": f"{len(report.unreadable_mfi)} row(s) had an illegible MFI value",
                "bead_ids": list(report.unreadable_mfi),
            }
        )

    return warnings

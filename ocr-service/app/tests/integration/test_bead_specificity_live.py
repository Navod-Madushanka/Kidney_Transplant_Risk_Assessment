# app/tests/integration/test_bead_specificity_live.py
#
# Real call against a live Ollama + qwen3-vl:4b-nothink -- excluded from
# the default `pytest` run. Run explicitly: `uv run pytest -m integration -v -s`
# (the -s is important here -- these tests print the per-run distribution,
# which is the actual point of this file; without -s pytest swallows it).
#
# COST WARNING, confirmed 2026-08-01: with tile concurrency bounded to 1
# (see app/extraction/llm_extract.py's CONCURRENT_TILE_LIMIT -- a real,
# necessary fix, not something to undo casually), each bead-specificity
# call runs its 8 row-band tiles sequentially. A real run of this file at
# RUNS=5 (5 repeats x 2 pages x 8 tiles = 80 real slow LLM calls, plus
# HLA/crossmatch) took **73 minutes** on the dev RTX 2060. RUNS=3 below
# cuts that to roughly 45 min for this file alone -- still genuinely slow,
# because bead specificity itself is slow per the "30s-2min per document"
# budget stated at the top of this doc, now paid 8x per page since tiles
# no longer overlap in wall-clock time. Don't run this file casually; it's
# for deliberately characterizing bead specificity's behavior, not a
# routine check. `uv run pytest` (no -m integration) skips it entirely.
import statistics

import pytest

from app.extraction.llm_extract import BEAD_SPECIFICITY_ALWAYS_VERIFY_WARNING, extract_bead_specificity
from app.tests.integration._scoring import score_anchors

pytestmark = pytest.mark.integration

# Per claude/ocr-to-local-llm-migration-plan.md's Phase 3 Post-Deployment
# Debugging: real production runs against sample_mfi_page1.jpg swung
# 10/13 -> 1/13 -> 2/13 -> 2/13 across four separate attempts (including
# before/after a real concurrency bug fix that eliminated most tile
# timeouts but did NOT fix overall accuracy). Single runs of this document
# type are demonstrably NOT reliable signal on their own -- this test
# characterizes the real distribution across N runs instead of gating a
# pass/fail on one. Only a minimal sanity floor is asserted (mean > 0,
# the mandatory verify warning always present) -- this is a
# monitoring/characterization test, not an accuracy gate, matching the
# decision already made to ship this document type as a flagged
# AI-assisted draft rather than block on hitting a number here.
#
# LOWERED 2026-08-01 (5 -> 3) after a real RUNS=5 run cost 73 minutes --
# see the COST WARNING above. 3 is still enough to see whether a page
# behaves like page1 did for real (good once, then flat) or like page2
# (flat throughout) without paying for 5. Raise back to 5+ only when you
# deliberately want a fuller distribution and have the time budget for it.
RUNS = 3


async def test_bead_specificity_page1_repeated_runs(bead_specificity_page1_bytes, bead_specificity_anchors):
    anchors = bead_specificity_anchors["page1_anchors"]
    scores = []
    for i in range(RUNS):
        structured = await extract_bead_specificity(bead_specificity_page1_bytes)
        assert BEAD_SPECIFICITY_ALWAYS_VERIFY_WARNING in structured["warning"]
        matched, total = score_anchors(structured["bead_specificity"], anchors)
        scores.append(matched)
        print(f"page1 run {i + 1}/{RUNS}: {matched}/{total} anchors matched")

    print(
        f"page1 distribution over {RUNS} runs: {scores} "
        f"(mean={statistics.mean(scores):.1f}, min={min(scores)}, max={max(scores)})"
    )
    assert statistics.mean(scores) > 0, (
        "every run scored zero anchors -- this looks like a real regression "
        "(e.g. tiling/prompt/model broken), not the already-documented variance"
    )


async def test_bead_specificity_page2_repeated_runs(bead_specificity_page2_bytes, bead_specificity_anchors):
    anchors = bead_specificity_anchors["page2_anchors"]
    scores = []
    for i in range(RUNS):
        structured = await extract_bead_specificity(bead_specificity_page2_bytes)
        assert BEAD_SPECIFICITY_ALWAYS_VERIFY_WARNING in structured["warning"]
        matched, total = score_anchors(structured["bead_specificity"], anchors)
        scores.append(matched)
        print(f"page2 run {i + 1}/{RUNS}: {matched}/{total} anchors matched")

    print(
        f"page2 distribution over {RUNS} runs: {scores} "
        f"(mean={statistics.mean(scores):.1f}, min={min(scores)}, max={max(scores)})"
    )
    assert statistics.mean(scores) > 0, (
        "every run scored zero anchors -- this looks like a real regression "
        "(e.g. tiling/prompt/model broken), not the already-documented variance"
    )

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
# call runs its 8 row-band tiles sequentially (DEFAULT_NUM_TILES in
# app/extraction/tiling.py -- briefly tried at 6 on 2026-08-03 to cut
# runtime, reverted after it cost real row coverage without a reliably
# faster full-batch result; see that file's docstring). A real run of
# this file at RUNS=5 (5 repeats x 2 pages x 8 tiles = 80 real slow LLM
# calls, plus HLA/crossmatch) took **73 minutes** on the dev RTX 2060.
# RUNS=3 below cuts that to roughly 45 min for this file alone -- still
# genuinely slow, because bead specificity itself is slow per the
# "30s-2min per document" budget stated at the top of this doc, now paid
# 8x per page since tiles no longer overlap in wall-clock time. Don't run
# this file casually; it's for deliberately characterizing bead
# specificity's behavior, not a routine check. `uv run pytest` (no -m
# integration) skips it entirely.
import statistics

import pytest

from app.extraction.llm_extract import BEAD_SPECIFICITY_ALWAYS_VERIFY_WARNING, extract_bead_specificity
from app.tests.integration._scoring import score_anchors

pytestmark = pytest.mark.integration

# Part I: bead_specificity_anchor.json deliberately does NOT carry bead IDs
# for its existing antigen/MFI anchors. Real attempts at reading them off
# the source images for this fixture found the Bead column's small print
# genuinely unreliable to transcribe with confidence (ambiguous digits at
# this resolution/blur) -- and a WRONG fabricated "ground truth" bead ID
# baked into a test fixture is worse than not having one, since it would
# look authoritative while actively misleading future debugging. The
# anchor-based scoring below is therefore still the pre-Part-I fuzzy
# antigen/MFI match (see _scoring.py) and stays structurally blind to
# duplicate-row creation on its own, same as before.
#
# What DOES directly test the Part I finding without needing fabricated
# ground truth: reconciliation's own bead-ID uniqueness invariant. Once
# reconcile_bead_rows groups by bead ID, no bead ID can legitimately
# appear twice in its output BY CONSTRUCTION -- so if it ever does, that's
# a real bug in the reconciliation/grouping logic itself, not a scoring
# nuance, and doesn't need anchor ground truth to catch. See
# test_bead_specificity_page1_repeated_runs/page2 below.

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


def _assert_no_duplicate_or_out_of_range_bead_ids(rows: list[dict]) -> None:
    """The structural check Part I actually needs: reconcile_bead_rows
    groups by bead ID, so a bead ID appearing twice in its OUTPUT is a
    reconciliation bug (grouping failed), not scoring noise -- catchable
    without any anchor ground truth. Also sanity-checks every present ID
    falls inside the panel range coerce_bead_id enforces (1..120); a
    result outside that range would mean coerce_bead_id was bypassed
    somehow."""
    bead_ids = [row["bead"] for row in rows if row.get("bead") is not None]
    assert len(bead_ids) == len(set(bead_ids)), (
        f"duplicate bead ID(s) in reconciled output: "
        f"{[b for b in bead_ids if bead_ids.count(b) > 1]}"
    )
    for bead_id in bead_ids:
        assert 1 <= int(bead_id) <= 120, f"bead ID {bead_id} outside the valid panel range"


async def test_bead_specificity_page1_repeated_runs(bead_specificity_page1_bytes, bead_specificity_anchors):
    anchors = bead_specificity_anchors["page1_anchors"]
    scores = []
    for i in range(RUNS):
        structured = await extract_bead_specificity(bead_specificity_page1_bytes)
        warning_details = [w["detail"] for w in structured["warnings"]]
        assert any(BEAD_SPECIFICITY_ALWAYS_VERIFY_WARNING in detail for detail in warning_details)
        _assert_no_duplicate_or_out_of_range_bead_ids(structured["bead_specificity"])
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
        warning_details = [w["detail"] for w in structured["warnings"]]
        assert any(BEAD_SPECIFICITY_ALWAYS_VERIFY_WARNING in detail for detail in warning_details)
        _assert_no_duplicate_or_out_of_range_bead_ids(structured["bead_specificity"])
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

# app/tests/integration/test_hla_typing_live.py
#
# Real call against a live Ollama + qwen3-vl:4b-nothink (needs `docker
# compose up` running locally, or ocr_base_url pointed at one -- excluded
# from the default `pytest` run, see [tool.pytest.ini_options] in
# pyproject.toml). Run explicitly: `uv run pytest -m integration -v`.
import pytest

from app.extraction.llm_extract import extract_hla_typing

pytestmark = pytest.mark.integration


async def test_hla_typing_full_extraction(hla_image_bytes, hla_ground_truth):
    """Confirmed 2026-08-01 in real production testing (see
    claude/ocr-to-local-llm-migration-plan.md, Phase 3): 64/64 fields
    exact match against sample_report.jpg. This test locks that in as a
    regression guard -- unlike bead specificity, this document type has
    shown no run-to-run variance in practice, so a single failing run here
    is a real signal worth investigating (prompt change, model swap,
    Ollama config drift), not noise to average away.

    MERGED 2026-08-01: this used to be two separate test functions, each
    making its own real (slow) call to extract_hla_typing -- doubling the
    cost for zero extra signal, since the 9-loci check below is implied by
    the exact-match assertion anyway. One real call, both checks."""
    structured = await extract_hla_typing(hla_image_bytes)

    assert structured["patient_details"] == hla_ground_truth["patient_details"]
    assert structured["donor_details"] == hla_ground_truth["donor_details"]
    assert structured["patient_hla"] == hla_ground_truth["patient_hla"]
    assert structured["donor_hla"] == hla_ground_truth["donor_hla"]
    assert "warning" not in structured

    # Guards specifically against the Phase 1 failure mode the prompt was
    # hardened for (HLA_TYPING_PROMPT's "count to 9" instruction) -- the
    # model initially truncated to 5/9 loci before that fix. Kept explicit
    # (rather than relying only on the exact-match assert above) so a
    # future ground-truth fixture change can't silently stop covering it.
    assert len(structured["patient_hla"]) == 9
    assert len(structured["donor_hla"]) == 9

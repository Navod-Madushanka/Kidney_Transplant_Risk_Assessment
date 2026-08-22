# app/tests/integration/test_crossmatch_live.py
#
# Real call against a live Ollama + qwen3-vl:4b-nothink -- excluded from
# the default `pytest` run. Run explicitly: `uv run pytest -m integration -v`.
#
# B8 (PDPA cleanup, FINALIZATION-PLAN.md Phase 3.4): _ACCEPTED_PATIENT_NAMES
# below and crossmatch_ground_truth's full_name/nic_number fields were the
# real patient/donor's real identity, transcribed from a real report image
# for this OCR-accuracy regression test. Both are now synthetic. If you
# have a real copy of the reference image locally, this test's very first
# assertion will now (correctly) fail, since the model will keep reading
# the real name off the real image and neither synthetic value will ever
# match it -- unlike test_hla_typing_live.py's fixture, this isn't a
# partial mismatch, it's total, because the model output was never
# decoupled from the name the way the ground-truth JSON's other fields are.
# Making this test meaningfully runnable again needs a redacted or
# synthetic reference image, not something fixable from this repo alone.
import pytest

from app.extraction.llm_extract import extract_crossmatch

pytestmark = pytest.mark.integration

_ACCEPTED_PATIENT_NAMES = {"Test Patient One"}


async def test_crossmatch_matches_ground_truth(crossmatch_image_bytes, crossmatch_ground_truth):
    """Confirmed 2026-08-01 in real production testing: 14/15 fields,
    matching Phase 1's spike result exactly, including which single field
    misses and why. If a future run misses a *different* field, that's a
    new regression worth investigating -- this test only tolerates the one
    specific, already-understood miss."""
    structured = await extract_crossmatch(crossmatch_image_bytes)

    assert structured["patient_details"]["full_name"] in _ACCEPTED_PATIENT_NAMES
    patient_rest = {k: v for k, v in structured["patient_details"].items() if k != "full_name"}
    ground_truth_rest = {
        k: v for k, v in crossmatch_ground_truth["patient_details"].items() if k != "full_name"
    }
    assert patient_rest == ground_truth_rest

    assert structured["donor_details"] == crossmatch_ground_truth["donor_details"]
    assert structured["crossmatch"] == crossmatch_ground_truth["crossmatch"]
    assert "warning" not in structured

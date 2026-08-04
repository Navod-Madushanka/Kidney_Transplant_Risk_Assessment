# app/tests/unit/test_ocr_schemas.py
from app.schemas.ocr import BeadSpecificityEntryOcr, OcrBatchExtractResponse


def test_bead_specificity_entry_accepts_real_ocr_service_shape():
    # Regression test for a real bug (fixed 2026-08-02): mfi used to be
    # typed `str`, but ocr-service actually emits it as a JSON number or
    # null (see _coerce_mfi in ocr-service/app/extraction/llm_extract.py),
    # which made /ocr/extract-batch 500 on every real bead-specificity
    # chart -- a populated numeric MFI is the normal case, not an edge case.
    entry = BeadSpecificityEntryOcr(antigen="A23", mfi=23706.91)
    assert entry.mfi == 23706.91

    illegible = BeadSpecificityEntryOcr(antigen="B45,Bw6", mfi=None)
    assert illegible.mfi is None


def test_batch_response_accepts_a_full_real_bead_specificity_list():
    response = OcrBatchExtractResponse(
        bead_specificity=[
            {"antigen": "A23", "mfi": 23706.91},
            {"antigen": "DQ4", "mfi": 0.0},
            {"antigen": "DP1", "mfi": None},
        ]
    )
    assert [e.mfi for e in response.bead_specificity] == [23706.91, 0.0, None]

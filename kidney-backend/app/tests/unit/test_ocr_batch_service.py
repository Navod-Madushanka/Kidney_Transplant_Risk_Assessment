# app/tests/unit/test_ocr_batch_service.py
"""Unit coverage for run_batch_extraction's merge logic, using a fake
call_ocr_service (monkeypatched) so these run without a live ocr-service /
Ollama instance -- see app/tests/integration/test_*_live.py in ocr-service
itself for the real network-hitting coverage.
"""
from app.services import ocr_batch_service
from app.services.ocr_batch_service import run_batch_extraction

HLA_TYPING_RESPONSE = {
    "structured": {
        "patient_details": {"full_name": "Rev.A.Premarathna Thero", "nic_number": "198001610076"},
        "donor_details": {"full_name": "K.R.Bandara", "nic_number": "823275544v"},
        "patient_hla": [{"locus": "A", "allele_1": "29", "allele_2": "33"}],
        "donor_hla": [{"locus": "A", "allele_1": "33", "allele_2": "33"}],
    }
}

FAKE_FILE = (b"...", "file.jpg", "image/jpeg")


def _fake_call_ocr_service(responses_by_document_type):
    async def _fake(file_bytes, filename, content_type, document_type):
        return responses_by_document_type[document_type]

    return _fake


def _crossmatch_response(patient_nic: str, donor_nic: str) -> dict:
    return {
        "structured": {
            "patient_details": {"full_name": "Someone", "nic_number": patient_nic},
            "donor_details": {"full_name": "Someone Else", "nic_number": donor_nic},
            "crossmatch": {"t_cell_result": "Compatible", "b_cell_result": "Compatible"},
        }
    }


async def test_matching_nic_across_documents_raises_no_identity_warning(monkeypatch):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service(
            {
                "hla_typing_report": HLA_TYPING_RESPONSE,
                "crossmatch": _crossmatch_response("198001610076", "823275544v"),
            }
        ),
    )

    result = await run_batch_extraction(
        {"hla_typing_report": FAKE_FILE, "crossmatch_report": FAKE_FILE}
    )

    assert result.errors == []
    assert result.patient_details["full_name"] == "Rev.A.Premarathna Thero"


async def test_mismatched_patient_nic_across_documents_warns(monkeypatch):
    # Regression test for a real gap (fixed 2026-08-02): uploading a
    # crossmatch report for a different patient than the HLA typing report
    # used to merge silently -- the HLA report's identity would just win
    # via the gap-fill-only merge, with no signal anything was wrong.
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service(
            {
                "hla_typing_report": HLA_TYPING_RESPONSE,
                # a real NIC belonging to a completely different patient
                "crossmatch": _crossmatch_response("765811562V", "823275544v"),
            }
        ),
    )

    result = await run_batch_extraction(
        {"hla_typing_report": FAKE_FILE, "crossmatch_report": FAKE_FILE}
    )

    assert len(result.errors) == 1
    assert result.errors[0]["field"] == "patient_details"
    assert "765811562V" in result.errors[0]["message"]
    assert "198001610076" in result.errors[0]["message"]
    # Still returns the merged data -- this is a warning, not a hard failure.
    assert result.patient_details["full_name"] == "Rev.A.Premarathna Thero"


async def test_mismatched_donor_nic_across_documents_warns(monkeypatch):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service(
            {
                "hla_typing_report": HLA_TYPING_RESPONSE,
                "crossmatch": _crossmatch_response("198001610076", "199315003570"),
            }
        ),
    )

    result = await run_batch_extraction(
        {"hla_typing_report": FAKE_FILE, "crossmatch_report": FAKE_FILE}
    )

    assert len(result.errors) == 1
    assert result.errors[0]["field"] == "donor_details"


async def test_no_crossmatch_document_raises_no_identity_warning(monkeypatch):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service({"hla_typing_report": HLA_TYPING_RESPONSE}),
    )

    result = await run_batch_extraction({"hla_typing_report": FAKE_FILE})

    assert result.errors == []


async def test_case_and_whitespace_differences_are_not_flagged_as_mismatches(monkeypatch):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service(
            {
                "hla_typing_report": HLA_TYPING_RESPONSE,
                "crossmatch": _crossmatch_response(" 198001610076 ", "823275544V"),
            }
        ),
    )

    result = await run_batch_extraction(
        {"hla_typing_report": FAKE_FILE, "crossmatch_report": FAKE_FILE}
    )

    assert result.errors == []

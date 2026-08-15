# app/tests/unit/test_ocr_batch_service.py
"""Unit coverage for run_batch_extraction's merge logic, using a fake
call_ocr_service (monkeypatched) so these run without a live ocr-service /
Ollama instance -- see app/tests/integration/test_*_live.py in ocr-service
itself for the real network-hitting coverage.
"""
import pytest

from app.services import ocr_batch_service
from app.services.ocr_batch_service import (
    DocumentChunk,
    ProgressEvent,
    run_batch_extraction,
    stream_batch_extraction,
)
from app.services.ocr_spool_service import SpooledUpload

HLA_TYPING_RESPONSE = {
    "structured": {
        "patient_details": {"full_name": "Rev.A.Premarathna Thero", "nic_number": "198001610076"},
        "donor_details": {"full_name": "K.R.Bandara", "nic_number": "823275544v"},
        "patient_hla": [{"locus": "A", "allele_1": "29", "allele_2": "33"}],
        "donor_hla": [{"locus": "A", "allele_1": "33", "allele_2": "33"}],
    }
}


@pytest.fixture
def fake_file(tmp_path) -> SpooledUpload:
    # call_ocr_service/call_ocr_service_stream are monkeypatched out in
    # every test below, so nothing ever actually opens this path -- it
    # only needs to look like a real spooled upload (Part G bounded-memory
    # pass: these functions take a SpooledUpload, not raw bytes, now).
    path = tmp_path / "file.jpg"
    path.write_bytes(b"...")
    return SpooledUpload(path=path, filename="file.jpg", content_type="image/jpeg")


def _fake_call_ocr_service(responses_by_document_type):
    async def _fake(upload, document_type):
        return responses_by_document_type[document_type]

    return _fake


def _fake_call_ocr_service_stream(structured_by_document_type, total_tiles=2):
    # Mirrors ocr-service's real /extract/stream contract (see
    # extract_bead_specificity_stream): one {"type": "progress", ...} per
    # tile starting at completed=0 (before any tile has run) through
    # completed=total_tiles, then a single final {"type": "result", ...}.
    async def _fake(upload, document_type):
        for completed in range(total_tiles + 1):
            yield {"type": "progress", "completed": completed, "total": total_tiles}
        yield {
            "type": "result",
            "document_type": document_type,
            "structured": structured_by_document_type[document_type],
        }

    return _fake


def _crossmatch_response(patient_nic: str, donor_nic: str) -> dict:
    return {
        "structured": {
            "patient_details": {"full_name": "Someone", "nic_number": patient_nic},
            "donor_details": {"full_name": "Someone Else", "nic_number": donor_nic},
            "crossmatch": {"t_cell_result": "Compatible", "b_cell_result": "Compatible"},
        }
    }


async def test_matching_nic_across_documents_raises_no_identity_warning(monkeypatch, fake_file):
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
        {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
    )

    assert result.errors == []
    assert result.patient_details["full_name"] == "Rev.A.Premarathna Thero"


async def test_mismatched_patient_nic_across_documents_warns(monkeypatch, fake_file):
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
        {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
    )

    assert len(result.errors) == 1
    assert result.errors[0]["field"] == "patient_details"
    assert "765811562V" in result.errors[0]["message"]
    assert "198001610076" in result.errors[0]["message"]
    # Still returns the merged data -- this is a warning, not a hard failure.
    assert result.patient_details["full_name"] == "Rev.A.Premarathna Thero"


async def test_mismatched_donor_nic_across_documents_warns(monkeypatch, fake_file):
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
        {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
    )

    assert len(result.errors) == 1
    assert result.errors[0]["field"] == "donor_details"


async def test_no_crossmatch_document_raises_no_identity_warning(monkeypatch, fake_file):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service({"hla_typing_report": HLA_TYPING_RESPONSE}),
    )

    result = await run_batch_extraction({"hla_typing_report": fake_file})

    assert result.errors == []


async def test_case_and_whitespace_differences_are_not_flagged_as_mismatches(
    monkeypatch, fake_file
):
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
        {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
    )

    assert result.errors == []


# ---------------------------------------------------------------------
# stream_batch_extraction — the generator run_batch_extraction is now
# built on top of. Phase 1.F speed pass (2026-08-05): lets a streaming
# HTTP endpoint surface each document's result as soon as it's ready
# instead of waiting for the whole batch.
# ---------------------------------------------------------------------

BEAD_SPECIFICITY_RESPONSE = {
    "structured": {
        "bead_specificity": [{"antigen": "A23", "mfi": 490.5}],
        "warning": "ai_extracted_verify_against_source_image",
    }
}


async def test_stream_yields_one_chunk_per_document_in_order(monkeypatch, fake_file):
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
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream(
            {"bead_specificity": BEAD_SPECIFICITY_RESPONSE["structured"]}
        ),
    )

    events = [
        event
        async for event in stream_batch_extraction(
            {
                "hla_typing_report": fake_file,
                "crossmatch_report": fake_file,
                "bead_specificity_page_1": fake_file,
            }
        )
    ]
    chunks = [e for e in events if isinstance(e, DocumentChunk)]

    assert [c.document_type for c in chunks] == [
        "hla_typing_report",
        "crossmatch_report",
        "bead_specificity_page_1",
    ]
    assert chunks[0].patient_details["full_name"] == "Rev.A.Premarathna Thero"
    assert chunks[0].patient_hla == [{"locus": "A", "allele_1": "29", "allele_2": "33"}]
    assert chunks[2].bead_specificity == [{"antigen": "A23", "mfi": 490.5}]


async def test_stream_emits_progress_events_before_each_document(monkeypatch, fake_file):
    # HLA typing/crossmatch are one LLM call each -- no intermediate
    # signal, so they only ever get a single completed=0/total=1 event.
    # Bead specificity relays real per-tile progress from
    # call_ocr_service_stream, ending at completed == total.
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
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream(
            {"bead_specificity": BEAD_SPECIFICITY_RESPONSE["structured"]}, total_tiles=3
        ),
    )

    events = [
        event
        async for event in stream_batch_extraction(
            {
                "hla_typing_report": fake_file,
                "crossmatch_report": fake_file,
                "bead_specificity_page_1": fake_file,
            }
        )
    ]
    progress = [e for e in events if isinstance(e, ProgressEvent)]

    assert [(p.document_type, p.completed, p.total) for p in progress] == [
        ("hla_typing_report", 0, 1),
        ("crossmatch_report", 0, 1),
        ("bead_specificity_page_1", 0, 3),
        ("bead_specificity_page_1", 1, 3),
        ("bead_specificity_page_1", 2, 3),
        ("bead_specificity_page_1", 3, 3),
    ]
    # Every ProgressEvent for a document comes strictly before that
    # document's DocumentChunk.
    for p in progress:
        chunk_index = next(
            i
            for i, e in enumerate(events)
            if isinstance(e, DocumentChunk) and e.document_type == p.document_type
        )
        assert events.index(p) < chunk_index


async def test_stream_crossmatch_chunk_only_carries_gap_fill_fields(monkeypatch, fake_file):
    # HLA typing already reported full_name/nic_number for both roles --
    # crossmatch's OWN (different) patient_details/donor_details must not
    # appear in its chunk at all, since the merge precedence (HLA typing
    # wins) has to survive being applied incrementally instead of via one
    # accumulating dict like before this refactor.
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

    events = [
        event
        async for event in stream_batch_extraction(
            {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
        )
    ]
    chunks = [e for e in events if isinstance(e, DocumentChunk)]

    crossmatch_chunk = chunks[1]
    assert crossmatch_chunk.patient_details == {}
    assert crossmatch_chunk.donor_details == {}
    assert crossmatch_chunk.crossmatch == {
        "t_cell_result": "Compatible",
        "b_cell_result": "Compatible",
    }


async def test_stream_crossmatch_chunk_gap_fills_when_hla_typing_missing_a_field(
    monkeypatch, fake_file
):
    hla_typing_missing_ref_no = {
        "structured": {
            **HLA_TYPING_RESPONSE["structured"],
            "patient_details": {
                **HLA_TYPING_RESPONSE["structured"]["patient_details"],
                "hla_ref_no": "",
            },
        }
    }
    crossmatch_with_ref_no = {
        "structured": {
            "patient_details": {"nic_number": "198001610076", "hla_ref_no": "847/26M"},
            "donor_details": {"nic_number": "823275544v"},
            "crossmatch": {"t_cell_result": "Compatible", "b_cell_result": "Compatible"},
        }
    }
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service(
            {
                "hla_typing_report": hla_typing_missing_ref_no,
                "crossmatch": crossmatch_with_ref_no,
            }
        ),
    )

    events = [
        event
        async for event in stream_batch_extraction(
            {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
        )
    ]
    chunks = [e for e in events if isinstance(e, DocumentChunk)]

    # nic_number was already (truthily) reported by HLA typing, so it's
    # excluded here -- only the genuinely-missing hla_ref_no gap-fills.
    assert chunks[1].patient_details == {"hla_ref_no": "847/26M"}


async def test_stream_crossmatch_chunk_carries_identity_mismatch_warning(monkeypatch, fake_file):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service(
            {
                "hla_typing_report": HLA_TYPING_RESPONSE,
                "crossmatch": _crossmatch_response("765811562V", "823275544v"),
            }
        ),
    )

    events = [
        event
        async for event in stream_batch_extraction(
            {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
        )
    ]
    chunks = [e for e in events if isinstance(e, DocumentChunk)]

    assert len(chunks[1].errors) == 1
    assert chunks[1].errors[0]["field"] == "patient_details"


async def test_stream_failed_document_yields_error_chunk_and_continues(monkeypatch, fake_file):
    async def _fake(upload, document_type):
        if document_type == "hla_typing_report":
            raise RuntimeError("Ollama unreachable")
        return _crossmatch_response("198001610076", "823275544v")

    monkeypatch.setattr(ocr_batch_service, "call_ocr_service", _fake)

    events = [
        event
        async for event in stream_batch_extraction(
            {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
        )
    ]
    chunks = [e for e in events if isinstance(e, DocumentChunk)]

    assert len(chunks) == 2
    assert chunks[0].document_type == "hla_typing_report"
    assert chunks[0].errors == [
        {"field": "hla_typing_report", "message": "OCR failed: Ollama unreachable"}
    ]
    assert chunks[0].patient_details == {}
    # One document failing doesn't stop the rest of the batch.
    assert chunks[1].document_type == "crossmatch_report"
    assert chunks[1].crossmatch == {"t_cell_result": "Compatible", "b_cell_result": "Compatible"}


async def test_run_batch_extraction_matches_streamed_chunks_merged(monkeypatch, fake_file):
    # Regression guard for the generator+wrapper refactor itself:
    # run_batch_extraction must still produce the same merged result as
    # manually folding together everything stream_batch_extraction yields.
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
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream(
            {"bead_specificity": BEAD_SPECIFICITY_RESPONSE["structured"]}
        ),
    )
    files = {
        "hla_typing_report": fake_file,
        "crossmatch_report": fake_file,
        "bead_specificity_page_1": fake_file,
        "bead_specificity_page_2": fake_file,
    }

    result = await run_batch_extraction(files)

    assert result.patient_details["full_name"] == "Rev.A.Premarathna Thero"
    assert result.donor_details["full_name"] == "K.R.Bandara"
    assert result.patient_hla == [{"locus": "A", "allele_1": "29", "allele_2": "33"}]
    assert result.crossmatch == {"t_cell_result": "Compatible", "b_cell_result": "Compatible"}
    # Bead specificity is uploaded twice (page 1 + page 2) -- both pages'
    # rows accumulate rather than overwrite.
    assert result.bead_specificity == [
        {"antigen": "A23", "mfi": 490.5},
        {"antigen": "A23", "mfi": 490.5},
    ]

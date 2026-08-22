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
    check_bead_id_uniqueness_across_pages,
    check_panel_antigen_consistency,
    run_batch_extraction,
    stream_batch_extraction,
)
from app.services.ocr_spool_service import SpooledUpload

HLA_TYPING_RESPONSE = {
    "structured": {
        "patient_details": {"full_name": "Test Patient One", "nic_number": "200000000001"},
        "donor_details": {"full_name": "Test Donor One", "nic_number": "000000000v"},
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
    # **kwargs absorbs extra_data (dsa_band_edges) -- this fake doesn't
    # need to do anything with it, only accept the same call shape the
    # real call_ocr_service_stream now has.
    async def _fake(upload, document_type, **kwargs):
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
                "crossmatch": _crossmatch_response("200000000001", "000000000v"),
            }
        ),
    )

    result = await run_batch_extraction(
        {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
    )

    assert result.errors == []
    assert result.patient_details["full_name"] == "Test Patient One"


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
                "crossmatch": _crossmatch_response("000000001V", "000000000v"),
            }
        ),
    )

    result = await run_batch_extraction(
        {"hla_typing_report": fake_file, "crossmatch_report": fake_file}
    )

    assert len(result.errors) == 1
    assert result.errors[0]["field"] == "patient_details"
    assert "000000001V" in result.errors[0]["message"]
    assert "200000000001" in result.errors[0]["message"]
    # Still returns the merged data -- this is a warning, not a hard failure.
    assert result.patient_details["full_name"] == "Test Patient One"


async def test_mismatched_donor_nic_across_documents_warns(monkeypatch, fake_file):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service(
            {
                "hla_typing_report": HLA_TYPING_RESPONSE,
                "crossmatch": _crossmatch_response("200000000001", "200000000002"),
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
                "crossmatch": _crossmatch_response(" 200000000001 ", "000000000V"),
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
                "crossmatch": _crossmatch_response("200000000001", "000000000v"),
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
    assert chunks[0].patient_details["full_name"] == "Test Patient One"
    assert chunks[0].patient_hla == [{"locus": "A", "allele_1": "29", "allele_2": "33"}]
    # page/panel are stamped from the slot (bead_specificity_page_1 ->
    # page 1/class_i) -- see SLOT_PAGE_PANEL.
    assert chunks[2].bead_specificity == [
        {"antigen": "A23", "mfi": 490.5, "page": 1, "panel": "class_i"}
    ]


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
                "crossmatch": _crossmatch_response("200000000001", "000000000v"),
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
                "crossmatch": _crossmatch_response("200000000001", "000000000v"),
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
            "patient_details": {"nic_number": "200000000001", "hla_ref_no": "847/26M"},
            "donor_details": {"nic_number": "000000000v"},
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
                "crossmatch": _crossmatch_response("000000001V", "000000000v"),
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
        return _crossmatch_response("200000000001", "000000000v")

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
                "crossmatch": _crossmatch_response("200000000001", "000000000v"),
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

    assert result.patient_details["full_name"] == "Test Patient One"
    assert result.donor_details["full_name"] == "Test Donor One"
    assert result.patient_hla == [{"locus": "A", "allele_1": "29", "allele_2": "33"}]
    assert result.crossmatch == {"t_cell_result": "Compatible", "b_cell_result": "Compatible"}
    # Bead specificity is uploaded twice (page 1 + page 2) -- both pages'
    # rows accumulate rather than overwrite, each stamped with its own
    # page/panel (see SLOT_PAGE_PANEL). Neither row carries a bead ID here
    # (the fake response doesn't set one), so the cross-page uniqueness
    # check has nothing to flag -- see
    # check_bead_id_uniqueness_across_pages, which only looks at rows
    # that DO have a bead ID.
    assert result.bead_specificity == [
        {"antigen": "A23", "mfi": 490.5, "page": 1, "panel": "class_i"},
        {"antigen": "A23", "mfi": 490.5, "page": 2, "panel": "class_ii"},
    ]


# ---------------------------------------------------------------------
# check_bead_id_uniqueness_across_pages -- the cross-page merge step
# (Part I, I7). Bead IDs repeat across the two panel pages by design (see
# SLOT_PAGE_PANEL's own comment), so (page, bead) rather than bead alone
# is the real identity once both pages are concatenated. This function
# only ASSERTS that invariant holds -- it must never dedupe, only warn.
# ---------------------------------------------------------------------


def test_same_bead_id_on_different_pages_is_not_a_conflict():
    # The real-chart case this whole mechanism exists for: bead 044 is a
    # distinct, unrelated antibody on each page (Class I vs Class II).
    rows = [
        {"bead": "044", "antigen": "B76,Bw6", "page": 1, "panel": "class_i"},
        {"bead": "044", "antigen": "DQ4", "page": 2, "panel": "class_ii"},
    ]

    assert check_bead_id_uniqueness_across_pages(rows) == []


def test_same_bead_id_repeated_on_the_same_page_is_flagged():
    # This should be structurally impossible (ocr-service's own
    # reconcile_bead_rows groups by bead within one page), so seeing it
    # here means that invariant broke somewhere -- worth surfacing, not
    # silently re-deduping.
    rows = [
        {"bead": "011", "antigen": "A24", "page": 1, "panel": "class_i"},
        {"bead": "011", "antigen": "A24", "page": 1, "panel": "class_i"},
    ]

    warnings = check_bead_id_uniqueness_across_pages(rows)

    assert len(warnings) == 1
    assert "011" in warnings[0]["message"]
    assert "page 1" in warnings[0]["message"]


def test_rows_without_a_bead_id_are_ignored():
    rows = [
        {"bead": None, "antigen": "A1", "page": 1, "panel": "class_i"},
        {"bead": None, "antigen": "A1", "page": 1, "panel": "class_i"},
    ]

    assert check_bead_id_uniqueness_across_pages(rows) == []


# ---------------------------------------------------------------------
# check_panel_antigen_consistency (B14) -- panel is stamped purely from
# page position (see SLOT_PAGE_PANEL); this cross-checks it against what
# the row's own antigen implies, so a swapped-page upload is flagged
# rather than silently mislabelling every row on that page.
# ---------------------------------------------------------------------


def test_class_i_antigen_on_class_i_panel_is_not_a_conflict():
    rows = [{"bead": "001", "antigen": "A23", "page": 1, "panel": "class_i"}]

    assert check_panel_antigen_consistency(rows) == []


def test_class_ii_antigen_on_class_ii_panel_is_not_a_conflict():
    rows = [{"bead": "001", "antigen": "DQ7", "page": 2, "panel": "class_ii"}]

    assert check_panel_antigen_consistency(rows) == []


def test_class_ii_antigen_stamped_class_i_is_flagged():
    # The pages were uploaded swapped: a DR antigen landed on the page 1
    # slot, which SLOT_PAGE_PANEL always stamps "class_i".
    rows = [{"bead": "012", "antigen": "DR13", "page": 1, "panel": "class_i"}]

    warnings = check_panel_antigen_consistency(rows)

    assert len(warnings) == 1
    assert "012" in warnings[0]["message"]
    assert "DR13" in warnings[0]["message"]
    assert "Class II" in warnings[0]["message"]
    assert "Class I" in warnings[0]["message"]


def test_class_i_antigen_stamped_class_ii_is_flagged():
    rows = [{"bead": "003", "antigen": "B76,Bw6", "page": 2, "panel": "class_ii"}]

    warnings = check_panel_antigen_consistency(rows)

    assert len(warnings) == 1
    assert "B76,Bw6" in warnings[0]["message"]


def test_antigen_on_a_locus_outside_the_recognized_scheme_is_not_checked():
    # A non-classical-HLA antigen (e.g. MICA) doesn't start with any of the
    # recognized serological prefixes (DR/DQ/DP/Cw/A/B), so
    # locus_for_antigen_designation returns None for it -- silently skipped
    # rather than guessed at, same precedent as the rest of this module.
    rows = [{"bead": "005", "antigen": "MICA1", "page": 1, "panel": "class_i"}]

    assert check_panel_antigen_consistency(rows) == []


def test_rows_missing_antigen_or_panel_are_ignored():
    rows = [
        {"bead": "006", "antigen": None, "page": 1, "panel": "class_i"},
        {"bead": "007", "antigen": "DR13", "page": 1, "panel": None},
    ]

    assert check_panel_antigen_consistency(rows) == []

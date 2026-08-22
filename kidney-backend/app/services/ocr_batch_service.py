# app/services/ocr_batch_service.py
from dataclasses import dataclass, field
from typing import AsyncIterator

from app.reference_data.dsa_threshold import DSA_SEVERITY_BANDS
from app.services.hla_typing_service import locus_for_antigen_designation
from app.services.ocr_client import call_ocr_service, call_ocr_service_stream
from app.services.ocr_spool_service import SpooledUpload

SLOT_DOCUMENT_TYPES = {
    "hla_typing_report": "hla_typing_report",
    "bead_specificity_page_1": "bead_specificity",
    "bead_specificity_page_2": "bead_specificity",
    "crossmatch_report": "crossmatch",
}

# Part I (bead-row identity / tile reconciliation): bead IDs repeat across
# the two bead-specificity pages -- each panel is numbered from 001
# independently (see ocr-service's bead_reconciliation.py docstring) -- so
# (page, bead), not bead alone, is the real row identity once both pages
# are merged. Derived from the SLOT, never from antigen content: a
# misread "DQ4" as "B44" must never silently reclassify which panel a row
# belongs to.
SLOT_PAGE_PANEL = {
    "bead_specificity_page_1": (1, "class_i"),
    "bead_specificity_page_2": (2, "class_ii"),
}

# Sent to ocr-service on every bead-specificity call so its tile-
# reconciliation conflict rule knows where the real DSA clinical-severity
# thresholds fall (see ocr_client.call_ocr_service_stream's docstring and
# ocr-service's bead_reconciliation._clinical_band). Computed once from
# the single source of truth this backend already owns -- never
# copy-pasted as a literal on the ocr-service side, so the two can't drift.
_DSA_BAND_EDGES_PARAM = ",".join(str(band.min_mfi) for band in DSA_SEVERITY_BANDS)


@dataclass
class BatchExtractionResult:
    patient_details: dict = field(default_factory=dict)
    donor_details: dict = field(default_factory=dict)
    patient_hla: list = field(default_factory=list)
    donor_hla: list = field(default_factory=list)
    bead_specificity: list = field(default_factory=list)
    crossmatch: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


@dataclass
class DocumentChunk:
    """One completed document's contribution — everything
    stream_batch_extraction yields. Same field shapes as
    BatchExtractionResult, but scoped to a single document rather than the
    whole batch, so a caller can surface it the moment it's ready instead
    of waiting for the rest of the batch to finish."""
    document_type: str  # the slot name, e.g. "bead_specificity_page_1"
    patient_details: dict = field(default_factory=dict)
    donor_details: dict = field(default_factory=dict)
    patient_hla: list = field(default_factory=list)
    donor_hla: list = field(default_factory=list)
    bead_specificity: list = field(default_factory=list)
    crossmatch: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


@dataclass
class ProgressEvent:
    """Emitted before a document's own DocumentChunk, so a streaming
    caller can show real in-progress feedback instead of a single
    0%->100% jump per document. Bead specificity pages are the only
    document type with a genuine intermediate signal (8 sequential
    tile calls, relayed from ocr-service's /extract/stream via
    call_ocr_service_stream) — completed climbs from 0 to total as tiles
    finish. HLA typing/crossmatch are one LLM call each, so they only
    ever emit a single completed=0, total=1 event right before the call
    starts; their completion is signaled by the DocumentChunk that
    follows, not a second progress event."""
    document_type: str  # the slot name, e.g. "bead_specificity_page_1"
    completed: int
    total: int


async def stream_batch_extraction(
    files: dict[str, SpooledUpload]
) -> AsyncIterator[DocumentChunk | ProgressEvent]:
    """files: {slot_name: SpooledUpload} — each upload already spooled to
    local disk by app/services/ocr_spool_service.py before this runs; see
    ocr_client.py for how it's streamed from there to ocr-service.

    Calls the OCR service ONCE PER FILE, awaited sequentially — not a
    PaddleOCR limitation (that engine was removed 2026-08-01, see
    claude/ocr-to-local-llm-migration-plan.md), but because ocr-service
    runs Ollama with OLLAMA_NUM_PARALLEL=1 and serialises every request
    behind its own semaphore (see ocr-service's app/api/routes.py) —
    firing these concurrently from here would only queue up behind that,
    not add throughput. A failure on one image is recorded in that
    document's chunk.errors and the rest of the batch still completes.

    Yields a ProgressEvent for a document before its DocumentChunk (see
    ProgressEvent's docstring), then the DocumentChunk once that document
    is ready, so a caller (e.g. a streaming HTTP endpoint) can surface
    both partial results and in-progress feedback instead of waiting for
    the whole batch. Crossmatch's patient_details/donor_details only ever
    contain GAP-FILL fields — anything HLA typing's chunk already reported
    (truthily) is deliberately left out of crossmatch's chunk, mirroring
    the merge precedence run_batch_extraction used to enforce in one
    accumulating dict, now tracked incrementally via
    known_patient_fields/known_donor_fields as chunks are produced.
    """
    hla_typing_structured: dict | None = None
    crossmatch_structured: dict | None = None
    known_patient_fields: dict = {}
    known_donor_fields: dict = {}

    for slot, upload in files.items():
        document_type = SLOT_DOCUMENT_TYPES[slot]
        chunk = DocumentChunk(document_type=slot)

        try:
            if document_type == "bead_specificity":
                structured: dict = {}
                async for event in call_ocr_service_stream(
                    upload, document_type, extra_data={"dsa_band_edges": _DSA_BAND_EDGES_PARAM}
                ):
                    if event["type"] == "progress":
                        yield ProgressEvent(
                            document_type=slot,
                            completed=event["completed"],
                            total=event["total"],
                        )
                    else:
                        structured = event["structured"]
            else:
                yield ProgressEvent(document_type=slot, completed=0, total=1)
                response = await call_ocr_service(upload, document_type)
                structured = response.get("structured", {})
        except Exception as exc:
            chunk.errors.append({"field": slot, "message": f"OCR failed: {exc}"})
            yield chunk
            continue

        # hla_typing_report/crossmatch still emit a single "warning" string;
        # bead_specificity emits a structured "warnings" list instead (Part
        # I -- see ocr-service's llm_extract._build_bead_warnings), since a
        # blanket string can't carry which beads a gap/conflict actually
        # affects. Both shapes fold into the same flat chunk.errors list.
        if structured.get("warning"):
            chunk.errors.append({"field": slot, "message": structured["warning"]})
        for warning in structured.get("warnings", []):
            chunk.errors.append({"field": slot, "message": warning.get("detail", "")})

        if document_type == "hla_typing_report":
            hla_typing_structured = structured
            chunk.patient_details = structured.get("patient_details", {})
            chunk.donor_details = structured.get("donor_details", {})
            chunk.patient_hla = structured.get("patient_hla", [])
            chunk.donor_hla = structured.get("donor_hla", [])
            known_patient_fields.update({k: v for k, v in chunk.patient_details.items() if v})
            known_donor_fields.update({k: v for k, v in chunk.donor_details.items() if v})

        elif document_type == "bead_specificity":
            # Stamped from the SLOT (see SLOT_PAGE_PANEL), never inferred
            # from antigen content -- ocr-service reconciles per page and
            # can't tell page 1 from page 2 on its own (both are sent as
            # the same document_type="bead_specificity").
            page, panel = SLOT_PAGE_PANEL.get(slot, (None, None))
            chunk.bead_specificity = [
                {**row, "page": page, "panel": panel}
                for row in structured.get("bead_specificity", [])
            ]

        elif document_type == "crossmatch":
            crossmatch_structured = structured
            # Gap-fill only — never override what the HLA typing report
            # already found.
            chunk.patient_details = {
                k: v
                for k, v in structured.get("patient_details", {}).items()
                if v and not known_patient_fields.get(k)
            }
            chunk.donor_details = {
                k: v
                for k, v in structured.get("donor_details", {}).items()
                if v and not known_donor_fields.get(k)
            }
            chunk.crossmatch = structured.get("crossmatch", {})
            chunk.errors.extend(
                _check_cross_document_identity(hla_typing_structured, crossmatch_structured)
            )

        yield chunk


async def run_batch_extraction(files: dict[str, SpooledUpload]) -> BatchExtractionResult:
    """Non-streaming callers: consumes stream_batch_extraction and merges
    every chunk into one final result — identical external behavior to
    before this function was refactored into a generator + wrapper.
    ProgressEvents carry nothing this result shape has room for, so they're
    just skipped."""
    result = BatchExtractionResult()

    async for item in stream_batch_extraction(files):
        if isinstance(item, ProgressEvent):
            continue
        chunk = item
        result.patient_details.update(chunk.patient_details)
        result.donor_details.update(chunk.donor_details)
        if chunk.patient_hla:
            result.patient_hla = chunk.patient_hla
        if chunk.donor_hla:
            result.donor_hla = chunk.donor_hla
        # Concatenates, never dedupes -- reconciliation already happened
        # PER PAGE inside ocr-service (it has the tiles); this cross-page
        # step's only job is to notice if the (page, bead) identity was
        # somehow violated, not to merge further. See
        # check_bead_id_uniqueness_across_pages.
        result.bead_specificity.extend(chunk.bead_specificity)
        if chunk.crossmatch:
            result.crossmatch = chunk.crossmatch
        result.errors.extend(chunk.errors)

    result.errors.extend(check_bead_id_uniqueness_across_pages(result.bead_specificity))
    result.errors.extend(check_panel_antigen_consistency(result.bead_specificity))
    return result


def check_bead_id_uniqueness_across_pages(rows: list[dict]) -> list[dict]:
    """Asserts (page, bead) is unique across the merged bead_specificity
    list, raising a WARNING (never dropping a row) if it isn't. This is
    deliberately not a second dedupe pass -- reconciliation already ran
    per page inside ocr-service, where the actual tiles are; concatenating
    both pages' already-reconciled rows should always satisfy this by
    construction. A violation here means that invariant broke somewhere
    (e.g. a slot-mapping bug), which is worth surfacing to the doctor
    rather than silently re-deduping and hiding it, same as I2's whole
    point about not making a real problem invisible.

    Public (not module-private) because ocr_job_service.py's
    _save_bead_specificity_if_present is the OTHER cross-page merge point
    (the registration-time auto-save path, restored with a guard after
    Part J -- see that function's docstring) and needs the identical
    check -- both call this rather than each keeping their own copy."""
    seen: dict[tuple, int] = {}
    for row in rows:
        bead = row.get("bead")
        if bead is None:
            continue
        key = (row.get("page"), bead)
        seen[key] = seen.get(key, 0) + 1

    duplicate_keys = sorted(key for key, count in seen.items() if count > 1)
    return [
        {
            "field": "bead_specificity",
            "message": (
                f"Bead {bead} on page {page} appears more than once after merging both "
                "pages -- please verify the bead specificity rows manually."
            ),
        }
        for page, bead in duplicate_keys
    ]


# B14: which serological locus each panel is expected to carry. A/B/C are
# Class I antigens; DR/DQ/DP are Class II -- see
# hla_typing_service.locus_for_antigen_designation for the antigen-string ->
# locus mapping this is built on. DRB3,4,5/DQA1/DPA1 aren't reachable
# through that function at all (it only recognizes the serological schemes
# in _SEROLOGICAL_LOCUS_PREFIX plus bare A/B), so a row on one of those loci
# is simply not checked here rather than guessed at.
_CLASS_I_LOCI = {"A", "B", "C"}
_CLASS_II_LOCI = {"DRB1", "DQB1", "DPB1"}
_LOCUS_TO_PANEL = {
    **{locus: "class_i" for locus in _CLASS_I_LOCI},
    **{locus: "class_ii" for locus in _CLASS_II_LOCI},
}
_PANEL_DISPLAY_LABEL = {"class_i": "Class I", "class_ii": "Class II"}


def check_panel_antigen_consistency(rows: list[dict]) -> list[dict]:
    """B14: panel (class_i/class_ii) is stamped purely from which page a row
    came from (see SLOT_PAGE_PANEL above) -- correct only if the lab
    actually printed Class I beads on page 1 and Class II on page 2, in
    that order. If a lab prints them in the other order, or a doctor
    uploads the two pages swapped, every row on that page is stamped with
    the wrong panel, and (panel, bead) row identity (see
    check_bead_id_uniqueness_across_pages) can silently collide with the
    other page's real rows instead of merely being wrong.

    Cross-checks the panel actually assigned against the antigen the row
    itself claims (A/B/C -> Class I; DR/DQ/DP -> Class II) and raises a
    WARNING -- never reassigns the panel or drops the row, same "surface
    it, don't silently fix or hide it" precedent as the rest of this
    module -- when they disagree, so a swapped upload is flagged for the
    doctor to resolve rather than trusting slot position blindly."""
    conflicts = []
    for row in rows:
        antigen = row.get("antigen")
        panel = row.get("panel")
        if not antigen or not panel:
            continue
        locus = locus_for_antigen_designation(antigen)
        expected_panel = _LOCUS_TO_PANEL.get(locus)
        if expected_panel is not None and expected_panel != panel:
            conflicts.append(
                {
                    "field": "bead_specificity",
                    "message": (
                        f"Bead {row.get('bead')} on page {row.get('page')} is antigen "
                        f"{antigen!r}, normally a {_PANEL_DISPLAY_LABEL[expected_panel]} antigen, "
                        f"but this row was stamped {_PANEL_DISPLAY_LABEL.get(panel, panel)} from "
                        "its page position -- the two bead-specificity pages may have been "
                        "uploaded in the wrong order. Please verify."
                    ),
                }
            )
    return conflicts


def _check_cross_document_identity(
    hla_typing_structured: dict | None, crossmatch_structured: dict | None
) -> list[dict]:
    """The HLA typing report and the crossmatch report are the only two
    document types that each independently extract a patient/donor
    identity. If a doctor uploads a crossmatch report for the wrong
    patient (e.g. picked up someone else's scan), the gap-fill merge above
    would otherwise silently keep the HLA typing report's identity while
    quietly absorbing the other document's crossmatch result — no signal
    that anything was wrong. NIC number is the most reliable identity
    anchor available here (far less OCR-ambiguous than a name), so when
    both documents produced one for the same role and they disagree,
    surface it as a warning rather than staying silent. This is
    deliberately non-blocking, consistent with every other warning in
    `errors` — the doctor still gets the merged data back and decides
    whether to proceed.
    """
    if not hla_typing_structured or not crossmatch_structured:
        return []

    warnings = []
    for role, person in (("patient_details", "patient"), ("donor_details", "donor")):
        hla_nic = (hla_typing_structured.get(role) or {}).get("nic_number", "")
        crossmatch_nic = (crossmatch_structured.get(role) or {}).get("nic_number", "")
        if hla_nic and crossmatch_nic and hla_nic.strip().upper() != crossmatch_nic.strip().upper():
            warnings.append(
                {
                    "field": role,
                    "message": (
                        f"The {person}'s NIC on the crossmatch report ({crossmatch_nic}) "
                        f"doesn't match the {person}'s NIC on the HLA typing report "
                        f"({hla_nic}). These documents may belong to different people; "
                        "please verify before continuing."
                    ),
                }
            )
    return warnings

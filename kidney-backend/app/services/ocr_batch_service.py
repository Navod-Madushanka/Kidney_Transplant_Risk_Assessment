# app/services/ocr_batch_service.py
from dataclasses import dataclass, field
from typing import AsyncIterator

from app.services.ocr_client import call_ocr_service, call_ocr_service_stream

SLOT_DOCUMENT_TYPES = {
    "hla_typing_report": "hla_typing_report",
    "bead_specificity_page_1": "bead_specificity",
    "bead_specificity_page_2": "bead_specificity",
    "crossmatch_report": "crossmatch",
}


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
    files: dict[str, tuple[bytes, str, str]]
) -> AsyncIterator[DocumentChunk | ProgressEvent]:
    """files: {slot_name: (file_bytes, filename, content_type)}.

    Calls the OCR service ONCE PER FILE, awaited sequentially — this is
    the queue: PaddleOCR can only process one image at a time, so we
    never fire concurrent requests at it. A failure on one image is
    recorded in that document's chunk.errors and the rest of the batch
    still completes.

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

    for slot, (file_bytes, filename, content_type) in files.items():
        document_type = SLOT_DOCUMENT_TYPES[slot]
        chunk = DocumentChunk(document_type=slot)

        try:
            if document_type == "bead_specificity":
                structured: dict = {}
                async for event in call_ocr_service_stream(
                    file_bytes, filename, content_type, document_type
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
                response = await call_ocr_service(file_bytes, filename, content_type, document_type)
                structured = response.get("structured", {})
        except Exception as exc:
            chunk.errors.append({"field": slot, "message": f"OCR failed: {exc}"})
            yield chunk
            continue

        if structured.get("warning"):
            chunk.errors.append({"field": slot, "message": structured["warning"]})

        if document_type == "hla_typing_report":
            hla_typing_structured = structured
            chunk.patient_details = structured.get("patient_details", {})
            chunk.donor_details = structured.get("donor_details", {})
            chunk.patient_hla = structured.get("patient_hla", [])
            chunk.donor_hla = structured.get("donor_hla", [])
            known_patient_fields.update({k: v for k, v in chunk.patient_details.items() if v})
            known_donor_fields.update({k: v for k, v in chunk.donor_details.items() if v})

        elif document_type == "bead_specificity":
            chunk.bead_specificity = structured.get("bead_specificity", [])

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


async def run_batch_extraction(files: dict[str, tuple[bytes, str, str]]) -> BatchExtractionResult:
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
        result.bead_specificity.extend(chunk.bead_specificity)
        if chunk.crossmatch:
            result.crossmatch = chunk.crossmatch
        result.errors.extend(chunk.errors)

    return result


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

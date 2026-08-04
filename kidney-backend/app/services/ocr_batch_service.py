# app/services/ocr_batch_service.py
from dataclasses import dataclass, field

from app.services.ocr_client import call_ocr_service

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


async def run_batch_extraction(files: dict[str, tuple[bytes, str, str]]) -> BatchExtractionResult:
    """files: {slot_name: (file_bytes, filename, content_type)}.

    Calls the OCR service ONCE PER FILE, awaited sequentially — this is
    the queue: PaddleOCR can only process one image at a time, so we
    never fire concurrent requests at it. A failure on one image is
    recorded in `errors` and the rest of the batch still completes.
    """
    result = BatchExtractionResult()
    hla_typing_structured: dict | None = None
    crossmatch_structured: dict | None = None

    for slot, (file_bytes, filename, content_type) in files.items():
        document_type = SLOT_DOCUMENT_TYPES[slot]
        try:
            response = await call_ocr_service(file_bytes, filename, content_type, document_type)
        except Exception as exc:
            result.errors.append({"field": slot, "message": f"OCR failed: {exc}"})
            continue

        structured = response.get("structured", {})
        if structured.get("warning"):
            result.errors.append({"field": slot, "message": structured["warning"]})

        if document_type == "hla_typing_report":
            hla_typing_structured = structured
            result.patient_details.update(structured.get("patient_details", {}))
            result.donor_details.update(structured.get("donor_details", {}))
            result.patient_hla = structured.get("patient_hla", result.patient_hla)
            result.donor_hla = structured.get("donor_hla", result.donor_hla)

        elif document_type == "bead_specificity":
            result.bead_specificity.extend(structured.get("bead_specificity", []))

        elif document_type == "crossmatch":
            crossmatch_structured = structured
            # Crossmatch demographics only fill gaps — never override what
            # the HLA typing report already found.
            for k, v in structured.get("patient_details", {}).items():
                if not result.patient_details.get(k):
                    result.patient_details[k] = v
            for k, v in structured.get("donor_details", {}).items():
                if not result.donor_details.get(k):
                    result.donor_details[k] = v
            result.crossmatch = structured.get("crossmatch", {})

    result.errors.extend(
        _check_cross_document_identity(hla_typing_structured, crossmatch_structured)
    )

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

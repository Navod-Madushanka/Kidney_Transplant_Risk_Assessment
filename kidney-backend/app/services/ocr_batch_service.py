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
            result.patient_details.update(structured.get("patient_details", {}))
            result.donor_details.update(structured.get("donor_details", {}))
            result.patient_hla = structured.get("patient_hla", result.patient_hla)
            result.donor_hla = structured.get("donor_hla", result.donor_hla)

        elif document_type == "bead_specificity":
            result.bead_specificity.extend(structured.get("bead_specificity", []))

        elif document_type == "crossmatch":
            # Crossmatch demographics only fill gaps — never override what
            # the HLA typing report already found.
            for k, v in structured.get("patient_details", {}).items():
                if not result.patient_details.get(k):
                    result.patient_details[k] = v
            for k, v in structured.get("donor_details", {}).items():
                if not result.donor_details.get(k):
                    result.donor_details[k] = v
            result.crossmatch = structured.get("crossmatch", {})

    return result
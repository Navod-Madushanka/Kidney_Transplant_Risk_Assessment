# app/schemas/ocr.py
import uuid

from pydantic import BaseModel


class HLAOcrEntry(BaseModel):
    locus: str
    allele_1: str
    allele_2: str


class PersonDetailsOcr(BaseModel):
    full_name: str = ""
    nic_number: str = ""
    date_of_birth: str = ""
    blood_type: str = ""
    hla_ref_no: str = ""


class OcrExtractResponse(BaseModel):
    patient_details: PersonDetailsOcr
    donor_details: PersonDetailsOcr
    patient_hla: list[HLAOcrEntry]
    donor_hla: list[HLAOcrEntry]


class BeadSpecificityEntryOcr(BaseModel):
    # bead -- the source chart's zero-padded 3-digit Bead code, or None if
    # ocr-service couldn't read/attach one (see coerce_bead_id in
    # ocr-service's bead_reconciliation.py). page/panel are stamped by
    # THIS backend from the upload slot (see ocr_batch_service.py's
    # SLOT_PAGE_PANEL), not by ocr-service, which can't tell page 1 from
    # page 2 on its own.
    bead: str | None = None
    antigen: str
    # ocr-service emits this as a plain JSON number, or null for a row it
    # couldn't read (see coerce_mfi in ocr-service/app/extraction/
    # bead_reconciliation.py) -- this used to be typed `str`, which made
    # /ocr/extract-batch 500 on every real bead-specificity chart, since a
    # populated MFI value is the normal case, not an edge case.
    mfi: float | None = None
    page: int | None = None
    panel: str | None = None
    # Every candidate MFI reconciliation saw when tiles disagreed on this
    # bead -- populated only when there was a genuine conflict (see
    # ocr-service's bead_reconciliation.ReconciledRow.conflict). `mfi`
    # above is always the highest candidate in that case, never averaged
    # or silently picked.
    conflict: list[float | None] | None = None


class CrossmatchOcr(BaseModel):
    t_cell_result: str = ""
    b_cell_result: str = ""
    interpretation: str = ""
    remarks: str = ""
    test_date: str = ""


class OcrBatchError(BaseModel):
    field: str
    message: str


class OcrBatchExtractResponse(BaseModel):
    patient_details: PersonDetailsOcr = PersonDetailsOcr()
    donor_details: PersonDetailsOcr = PersonDetailsOcr()
    patient_hla: list[HLAOcrEntry] = []
    donor_hla: list[HLAOcrEntry] = []
    bead_specificity: list[BeadSpecificityEntryOcr] = []
    crossmatch: CrossmatchOcr = CrossmatchOcr()
    errors: list[OcrBatchError] = []


class OcrJobCreateResponse(BaseModel):
    job_id: uuid.UUID


class OcrJobDocumentStatus(BaseModel):
    # "pending" (not started yet) | "in_progress" (see completed/total) | "done"
    status: str
    completed: int = 0
    total: int = 1
    patient_details: PersonDetailsOcr = PersonDetailsOcr()
    donor_details: PersonDetailsOcr = PersonDetailsOcr()
    patient_hla: list[HLAOcrEntry] = []
    donor_hla: list[HLAOcrEntry] = []
    bead_specificity: list[BeadSpecificityEntryOcr] = []
    crossmatch: CrossmatchOcr = CrossmatchOcr()
    errors: list[OcrBatchError] = []


class OcrJobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str  # "running" | "done" | "failed"
    documents: dict[str, OcrJobDocumentStatus] = {}
    error: str | None = None

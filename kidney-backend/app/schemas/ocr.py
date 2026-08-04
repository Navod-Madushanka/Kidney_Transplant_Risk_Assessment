# app/schemas/ocr.py
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
    antigen: str
    # ocr-service emits this as a plain JSON number, or null for a row it
    # couldn't read (see _coerce_mfi in ocr-service/app/extraction/
    # llm_extract.py) -- this used to be typed `str`, which made
    # /ocr/extract-batch 500 on every real bead-specificity chart, since a
    # populated MFI value is the normal case, not an edge case.
    mfi: float | None = None


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

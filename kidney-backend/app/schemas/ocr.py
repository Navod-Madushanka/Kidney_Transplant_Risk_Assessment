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
    mfi: str


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
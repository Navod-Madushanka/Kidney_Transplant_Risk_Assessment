# app/schemas/ocr.py
from pydantic import BaseModel


class HLAOcrEntry(BaseModel):
    locus: str
    allele_1: str
    allele_2: str


class PersonDetailsOcr(BaseModel):
    full_name: str
    nic_number: str
    date_of_birth: str
    blood_type: str


class OcrExtractResponse(BaseModel):
    patient_details: PersonDetailsOcr
    donor_details: PersonDetailsOcr
    patient_hla: list[HLAOcrEntry]
    donor_hla: list[HLAOcrEntry]# app/schemas/ocr.py
from pydantic import BaseModel


class HLAOcrEntry(BaseModel):
    locus: str
    allele_1: str
    allele_2: str


class PersonDetailsOcr(BaseModel):
    full_name: str
    nic_number: str
    date_of_birth: str
    blood_type: str


class OcrExtractResponse(BaseModel):
    patient_details: PersonDetailsOcr
    donor_details: PersonDetailsOcr
    patient_hla: list[HLAOcrEntry]
    donor_hla: list[HLAOcrEntry]
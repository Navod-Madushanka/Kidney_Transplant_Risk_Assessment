# app/schemas/hla_typing.py
from pydantic import BaseModel

from app.models.enums import HLALocusEnum


class HLATypingEntry(BaseModel):
    locus: HLALocusEnum
    allele_1: str
    allele_2: str
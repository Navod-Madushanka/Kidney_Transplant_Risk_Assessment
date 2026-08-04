# app/models/enums.py
import enum

from app.reference_data.hla_loci import HLA_LOCI
from app.reference_data.sensitization_weights import SENSITIZATION_EVENT_WEIGHTS


class BloodType(str, enum.Enum):
    O = "O"  # noqa: E741 — real ABO blood type, not an ambiguous variable name
    A = "A"
    B = "B"
    AB = "AB"

class RhFactor(str, enum.Enum):
    POSITIVE = "+"
    NEGATIVE = "-"


class DonorStatus(str, enum.Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    TRANSPLANTED = "transplanted"


class ReportFileCategory(str, enum.Enum):
    HLA_TYPING_REPORT = "hla_typing_report"
    CROSSMATCH_REPORT = "crossmatch_report"
    BEAD_SPECIFICITY_CHART = "bead_specificity_chart"
    OTHER = "other"


class HLALocusEnum(str, enum.Enum):
    DRB1 = "DRB1"
    B = "B"
    DQB1 = "DQB1"
    C = "C"
    A = "A"
    DRB3_4_5 = "DRB3,4,5"
    DQA1 = "DQA1"
    DPA1 = "DPA1"
    DPB1 = "DPB1"


assert set(member.value for member in HLALocusEnum) == set(
    HLA_LOCI
), "HLALocusEnum and HLA_LOCI have drifted out of sync"


class SensitizationEventTypeEnum(str, enum.Enum):
    PREVIOUS_TRANSPLANT = "previous_transplant"
    PREGNANCY = "pregnancy"
    BLOOD_TRANSFUSION = "blood_transfusion"


assert set(member.value for member in SensitizationEventTypeEnum) == set(
    SENSITIZATION_EVENT_WEIGHTS.keys()
), "SensitizationEventTypeEnum and SENSITIZATION_EVENT_WEIGHTS have drifted out of sync"

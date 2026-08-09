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
    # Added 2026-08-08: the 3-value set above couldn't represent a donor
    # mid-evaluation, ruled out, or no longer participating -- doctors had
    # nowhere to put that except leaving a stale "reserved"/"available",
    # which reads as "still in play" indefinitely. All four are terminal or
    # doctor-driven states, set the same way as the existing ones (PUT
    # /donors/{id}/status, no automatic transitions) -- see donor_service.py.
    UNDER_WORKUP = "under_workup"
    MEDICALLY_UNFIT = "medically_unfit"
    WITHDRAWN = "withdrawn"
    DECEASED = "deceased"


class Sex(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"


class Race(str, enum.Enum):
    # Added 2026-08-09 for the donor safety-assessment risk projection (see
    # services/donor_risk_service.py). BLACK/WHITE are the only two
    # categories the underlying model (Grams et al., NEJM 2016) has
    # published coefficients for -- OTHER exists so every donor can still
    # get a result, scored against the WHITE coefficients as the best
    # available stand-in. This is a real extrapolation, not a validated
    # third category: the model has no non-US validation at all, and this
    # app's NIC-registered donors aren't the US population it was built on
    # regardless of which value is selected here. The risk-assessment
    # screen surfaces that as a permanent disclaimer rather than treating
    # OTHER as just another option.
    BLACK = "black"
    WHITE = "white"
    OTHER = "other"


class SmokingStatus(str, enum.Enum):
    # Replaces the old is_smoker boolean (removed 2026-08-09): the donor
    # risk-projection model scores former and current smokers differently
    # (coefficients 0.3700 vs 0.5680), which a yes/no flag can't represent.
    NEVER = "never"
    FORMER = "former"
    CURRENT = "current"


class ReportFileCategory(str, enum.Enum):
    HLA_TYPING_REPORT = "hla_typing_report"
    CROSSMATCH_REPORT = "crossmatch_report"
    # Split into two dedicated pages (rather than one "bead_specificity_chart"
    # slot) to mirror the compatibility-check wizard's own two bead-specificity
    # upload slots (see PhotoUploadsStep.jsx's UPLOAD_SLOTS) -- a chart that
    # runs to a second page needs both pages archived to feed OCR extraction
    # completely.
    BEAD_SPECIFICITY_CHART_PAGE_1 = "bead_specificity_chart_page_1"
    BEAD_SPECIFICITY_CHART_PAGE_2 = "bead_specificity_chart_page_2"
    OTHER = "other"


class OcrExtractionJobStatus(str, enum.Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


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

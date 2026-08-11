# app/services/donor_risk_input_adapter.py
"""
Single place that builds donor_risk_service.DonorRiskAssessmentInput from a
Donor ORM row -- deliberately NOT inside donor_risk_service.py itself,
which is a pure scoring service that never imports app.models (see its own
module docstring) so it stays testable without a database. Mirrors
lkdpi_input_adapter.py's split for the same reason.

Was previously hand-rolled once, privately, inside app/api/donors.py's
_build_donor_risk_input -- extracted here so the compatibility readiness
endpoint (app/services/compatibility_precondition_service.py) can reuse the
exact same conversion instead of a second copy.
"""

from app.models.donor import Donor
from app.services.donor_risk_service import DonorRiskAssessmentInput, calculate_age_years


def donor_risk_input_from_record(donor: Donor) -> DonorRiskAssessmentInput:
    """Enum columns become their .value string, age is derived from
    date_of_birth. Numeric(...) columns come back from SQLAlchemy as
    decimal.Decimal, not float -- converted explicitly here (mixing Decimal
    and float in donor_risk_service's arithmetic raises TypeError
    otherwise)."""
    return DonorRiskAssessmentInput(
        age_years=calculate_age_years(donor.date_of_birth),
        sex=donor.sex.value if donor.sex else None,
        race=donor.race.value if donor.race else None,
        egfr=float(donor.egfr) if donor.egfr is not None else None,
        systolic_bp=donor.systolic_bp,
        diastolic_bp=donor.diastolic_bp,
        is_on_antihypertensive_medication=donor.is_on_antihypertensive_medication,
        bmi=float(donor.bmi) if donor.bmi is not None else None,
        has_diabetes=donor.has_diabetes,
        urine_acr=float(donor.urine_acr) if donor.urine_acr is not None else None,
        smoking_status=donor.smoking_status.value if donor.smoking_status else None,
        family_history_kidney_disease=donor.family_history_kidney_disease,
    )

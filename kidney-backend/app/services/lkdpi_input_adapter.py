# app/services/lkdpi_input_adapter.py
"""
Single place that builds lkdpi_service.LKDPIInput from a Donor/Patient ORM
pair -- deliberately NOT inside lkdpi_service.py itself, which is a pure
scoring service that never imports app.models (see its own module
docstring) so it stays testable without a database. This adapter is the
DB-facing seam other services sit behind.

Three call sites need this exact conversion (donor_age from date_of_birth,
Decimal->float coercion, HLA-B/DRB1 counts from a mismatch_result) --
match_pipeline.py, exchange_graph_service.py, and the compatibility
readiness endpoint (app/services/compatibility_precondition_service.py).
They used to each hand-roll it; two copies had already drifted apart in
review, so this is the third and last.
"""

from app.models.donor import Donor
from app.models.patient import Patient
from app.services.donor_risk_service import calculate_age_years
from app.services.hla_mismatch_service import MismatchResult
from app.services.lkdpi_service import LKDPIInput


def _locus_mismatch_count(mismatch_result: MismatchResult, locus: str) -> int | None:
    for detail in mismatch_result.locus_breakdown:
        if detail.locus == locus:
            return detail.unique_mismatches
    return None


def lkdpi_input_from_records(
    donor: Donor,
    patient: Patient,
    mismatch_result: MismatchResult,
    *,
    abo_incompatible: bool,
) -> LKDPIInput:
    """Numeric(...) columns come back from SQLAlchemy as decimal.Decimal,
    not float -- converted explicitly here, same as _build_donor_risk_input
    in app/api/donors.py. HLA-B/HLA-DR(DRB1) mismatch counts are read from
    the caller's own mismatch_result rather than recounted."""
    return LKDPIInput(
        donor_age_years=calculate_age_years(donor.date_of_birth),
        donor_egfr=float(donor.egfr) if donor.egfr is not None else None,
        donor_bmi=float(donor.bmi) if donor.bmi is not None else None,
        donor_race=donor.race.value if donor.race else None,
        donor_smoking_status=donor.smoking_status.value if donor.smoking_status else None,
        donor_systolic_bp=float(donor.systolic_bp) if donor.systolic_bp is not None else None,
        donor_sex=donor.sex.value if donor.sex else None,
        recipient_sex=patient.sex.value if patient.sex else None,
        abo_incompatible=abo_incompatible,
        donor_biologically_related=donor.is_biologically_related,
        hla_b_mismatches=_locus_mismatch_count(mismatch_result, "B"),
        hla_dr_mismatches=_locus_mismatch_count(mismatch_result, "DRB1"),
        donor_weight_kg=float(donor.weight_kg) if donor.weight_kg is not None else None,
        recipient_weight_kg=float(patient.weight_kg) if patient.weight_kg is not None else None,
    )

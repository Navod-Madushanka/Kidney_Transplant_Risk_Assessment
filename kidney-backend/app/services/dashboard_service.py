# app/services/dashboard_service.py
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.match_report import MatchReport
from app.models.patient import Patient
from app.schemas.dashboard import (
    LatestReportSummary,
    PatientWithLatestReport,
    RecentReportSummary,
)
from app.services.risk_tier_service import get_risk_tier


def _derive_risk_tier(hla_scoring_result: Optional[dict]) -> Optional[str]:
    """MatchReport doesn't persist risk_tier as its own column (only the
    raw hla_scoring_result JSON), so it's re-derived here from the stored
    total_score using the same RISK_TIERS boundaries the pipeline used at
    report time. Halted reports (ABO fail / DSA trigger) never reach HLA
    scoring, so hla_scoring_result is None for those and this returns None.
    """
    if not hla_scoring_result:
        return None
    return get_risk_tier(hla_scoring_result["total_score"])


def _lkdpi_score_and_band(lkdpi_result: Optional[dict]) -> tuple[Optional[float], Optional[str]]:
    """lkdpi_result is None both for halted reports (nothing scored) and
    for has_sufficient_data=False ones (missing inputs) -- either way there
    is no score/band to surface here."""
    if not lkdpi_result or not lkdpi_result.get("has_sufficient_data"):
        return None, None
    return lkdpi_result.get("score"), lkdpi_result.get("band")


async def get_patients_with_latest_report(
    db: AsyncSession, doctor_id: uuid.UUID
) -> list[PatientWithLatestReport]:
    patients_result = await db.execute(
        select(Patient)
        .where(Patient.doctor_id == doctor_id, Patient.is_deleted.is_(False))
        .order_by(Patient.full_name)
    )
    patients = list(patients_result.scalars().all())

    if not patients:
        return []

    patient_ids = [p.id for p in patients]

    # DISTINCT ON (Postgres-specific, matches this app's Postgres-only setup)
    # picks exactly one row per patient_id: the most recent one, since rows
    # are ordered by patient_id then created_at desc within each group.
    latest_reports_result = await db.execute(
        select(MatchReport)
        .where(MatchReport.patient_id.in_(patient_ids))
        .distinct(MatchReport.patient_id)
        .order_by(MatchReport.patient_id, MatchReport.created_at.desc())
    )
    latest_reports_by_patient = {
        report.patient_id: report for report in latest_reports_result.scalars().all()
    }

    results = []
    for patient in patients:
        report = latest_reports_by_patient.get(patient.id)
        latest_report = None
        if report is not None:
            lkdpi_score, lkdpi_band = _lkdpi_score_and_band(report.lkdpi_result)
            latest_report = LatestReportSummary(
                id=report.id,
                overall_status=report.overall_status,
                risk_tier=_derive_risk_tier(report.hla_scoring_result),
                final_risk_level=report.final_risk_level,
                outcome=report.outcome,
                lkdpi_score=lkdpi_score,
                lkdpi_band=lkdpi_band,
                created_at=report.created_at,
            )

        results.append(
            PatientWithLatestReport(
                id=patient.id,
                full_name=patient.full_name,
                blood_type=patient.blood_type,
                nic_number=patient.nic_number,
                latest_report=latest_report,
            )
        )

    return results


async def get_recent_reports_for_doctor(
    db: AsyncSession, doctor_id: uuid.UUID, limit: int = 5
) -> list[RecentReportSummary]:
    result = await db.execute(
        select(MatchReport, Patient, Donor)
        .join(Patient, Patient.id == MatchReport.patient_id)
        .join(Donor, Donor.id == MatchReport.donor_id)
        .where(
            Patient.doctor_id == doctor_id,
            Patient.is_deleted.is_(False),
            Donor.is_deleted.is_(False),
        )
        .order_by(MatchReport.created_at.desc())
        .limit(limit)
    )

    summaries = []
    for report, patient, donor in result.all():
        # donor.doctor_id can differ from doctor_id for a cross-hospital
        # match report (see donor_search_service.py) — never surface a
        # non-owned donor's real identity on this doctor's own dashboard.
        donor_full_name = (
            donor.full_name if donor.doctor_id == doctor_id else "External donor"
        )
        lkdpi_score, lkdpi_band = _lkdpi_score_and_band(report.lkdpi_result)
        summaries.append(
            RecentReportSummary(
                id=report.id,
                patient_id=patient.id,
                patient_full_name=patient.full_name,
                donor_id=donor.id,
                donor_full_name=donor_full_name,
                overall_status=report.overall_status,
                risk_tier=_derive_risk_tier(report.hla_scoring_result),
                final_risk_level=report.final_risk_level,
                outcome=report.outcome,
                lkdpi_score=lkdpi_score,
                lkdpi_band=lkdpi_band,
                created_at=report.created_at,
            )
        )

    return summaries

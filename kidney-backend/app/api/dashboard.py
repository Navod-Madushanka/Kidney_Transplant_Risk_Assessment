# app/api/dashboard.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.dashboard import PatientWithLatestReport, RecentReportSummary
from app.services.dashboard_service import (
    get_patients_with_latest_report,
    get_recent_reports_for_doctor,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/patients", response_model=list[PatientWithLatestReport])
async def get_dashboard_patients_endpoint(
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patients belonging to the current doctor, each with their most
    recent match report (if any) summarized inline — avoids the frontend
    needing an N+1 loop over /patients/{id}/reports just to show a badge.
    """
    return await get_patients_with_latest_report(db, current_doctor.id)


@router.get("/reports/recent", response_model=list[RecentReportSummary])
async def get_dashboard_recent_reports_endpoint(
    limit: int = 5,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Most recent match reports across all of the current doctor's
    patients, newest first, denormalized with patient/donor names.
    """
    return await get_recent_reports_for_doctor(db, current_doctor.id, limit=limit)
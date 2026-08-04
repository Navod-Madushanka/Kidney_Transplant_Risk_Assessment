# app/api/compatibility.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.match_report import CompatibilityCheckRequest, MatchReportResponse
from app.services.audit_service import create_audit_log
from app.services.donor_service import get_donor_for_compatibility_check
from app.services.match_pipeline import CrossmatchInputData, run_match_pipeline
from app.services.match_report_service import (
    create_match_report,
    get_match_report_by_id,
)
from app.services.patient_service import get_patient_by_id_for_doctor

router = APIRouter(prefix="/compatibility", tags=["compatibility"])


@router.post("/check", response_model=MatchReportResponse, status_code=status.HTTP_201_CREATED)
async def check_compatibility(
    payload: CompatibilityCheckRequest,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_by_id_for_doctor(db, payload.patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    donor = await get_donor_for_compatibility_check(db, payload.donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    crossmatch_input = None
    if payload.crossmatch is not None:
        crossmatch_input = CrossmatchInputData(
            is_positive=payload.crossmatch.is_positive,
            t_cell_result=payload.crossmatch.t_cell_result,
            b_cell_result=payload.crossmatch.b_cell_result,
            remarks=payload.crossmatch.remarks,
        )

    pipeline_result = await run_match_pipeline(
        db, patient, donor, crossmatch_input=crossmatch_input
    )

    report = await create_match_report(
        db, payload.patient_id, payload.donor_id, pipeline_result
    )

    is_cross_hospital = donor.doctor_id != current_doctor.id
    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="ran_cross_hospital_compatibility_check"
        if is_cross_hospital
        else "ran_compatibility_check",
        patient_id=payload.patient_id,
        donor_id=payload.donor_id,
        details={
            "match_report_id": str(report.id),
            "overall_status": report.overall_status,
            "cross_hospital": is_cross_hospital,
            "donor_doctor_id": str(donor.doctor_id),
        },
    )

    return MatchReportResponse.model_validate(report)


@router.get("/reports/{report_id}", response_model=MatchReportResponse)
async def get_report_endpoint(
    report_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await get_match_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    patient = await get_patient_by_id_for_doctor(db, report.patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    return MatchReportResponse.model_validate(report)

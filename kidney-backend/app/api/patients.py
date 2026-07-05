# app/api/patients.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.antibody_profile import AntibodyProfileEntry
from app.schemas.hla_typing import HLATypingEntry
from app.schemas.match_report import MatchReportResponse
from app.schemas.patient import PatientCreate, PatientResponse
from app.schemas.sensitization_event import (
    SensitizationEventEntry,
    SensitizationEventResponse,
)
from app.services.antibody_profile_service import replace_patient_antibody_profiles
from app.services.hla_typing_service import replace_patient_hla_typing
from app.services.match_report_service import get_reports_for_patient
from app.services.patient_service import create_patient, get_patient_by_id_for_doctor
from app.services.sensitization_event_service import create_sensitization_events

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_endpoint(
    payload: PatientCreate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await create_patient(db, current_doctor.id, payload)
    return PatientResponse.model_validate(patient)


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    return PatientResponse.model_validate(patient)


@router.put("/{patient_id}/hla-typings", status_code=status.HTTP_204_NO_CONTENT)
async def replace_patient_hla_typing_endpoint(
    patient_id: uuid.UUID,
    entries: list[HLATypingEntry],
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    await replace_patient_hla_typing(db, patient_id, entries)


@router.put("/{patient_id}/antibody-profiles", status_code=status.HTTP_204_NO_CONTENT)
async def replace_patient_antibody_profiles_endpoint(
    patient_id: uuid.UUID,
    entries: list[AntibodyProfileEntry],
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    await replace_patient_antibody_profiles(db, patient_id, entries)


@router.post(
    "/{patient_id}/sensitization-events",
    response_model=list[SensitizationEventResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_sensitization_events_endpoint(
    patient_id: uuid.UUID,
    entries: list[SensitizationEventEntry],
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    events = await create_sensitization_events(db, patient_id, entries)
    return [SensitizationEventResponse.model_validate(event) for event in events]


@router.get("/{patient_id}/reports", response_model=list[MatchReportResponse])
async def get_patient_reports_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    reports = await get_reports_for_patient(db, patient_id)
    return [MatchReportResponse.model_validate(report) for report in reports]
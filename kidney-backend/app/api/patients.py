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
from app.services.antibody_profile_service import (
    get_patient_antibody_profiles,
    replace_patient_antibody_profiles,
)
from app.services.hla_typing_service import (
    get_patient_hla_typing_entries,
    replace_patient_hla_typing,
)
from app.services.match_report_service import get_reports_for_patient
from app.services.patient_service import (
    create_patient,
    get_patient_by_id_for_doctor,
    get_patients_for_doctor,  # ← should now work
)
from app.services.sensitization_event_service import (
    create_sensitization_events,
    get_sensitization_events_for_patient,
)

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[PatientResponse])
async def list_patients_endpoint(
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all patients belonging to the current doctor."""
    patients = await get_patients_for_doctor(db, current_doctor.id)
    return [PatientResponse.model_validate(p) for p in patients]


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_endpoint(
    payload: PatientCreate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new patient for the current doctor."""
    patient = await create_patient(db, current_doctor.id, payload)
    return PatientResponse.model_validate(patient)


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a specific patient (only if owned by current doctor)."""
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
    """Replace HLA typing data for a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)
    await replace_patient_hla_typing(db, patient_id, entries)


@router.get("/{patient_id}/hla-typings", response_model=list[HLATypingEntry])
async def get_patient_hla_typings_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current HLA typing for a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)

    # Use the entries version instead of dict
    entries = await get_patient_hla_typing_entries(db, patient_id)

    # Convert model instances to schema
    return [
        HLATypingEntry.model_validate(entry) for entry in entries
    ]


@router.put("/{patient_id}/antibody-profiles", status_code=status.HTTP_204_NO_CONTENT)
async def replace_patient_antibody_profiles_endpoint(
    patient_id: uuid.UUID,
    entries: list[AntibodyProfileEntry],
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace antibody profile data for a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)
    await replace_patient_antibody_profiles(db, patient_id, entries)


@router.get("/{patient_id}/antibody-profiles", response_model=list[AntibodyProfileEntry])
async def get_patient_antibody_profiles_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current antibody profiles for a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)
    return await get_patient_antibody_profiles(db, patient_id)


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
    """Add new sensitization events for a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)

    events = await create_sensitization_events(db, patient_id, entries)
    return [SensitizationEventResponse.model_validate(event) for event in events]


@router.get("/{patient_id}/sensitization-events", response_model=list[SensitizationEventResponse])
async def list_patient_sensitization_events_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List sensitization events for a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)
    events = await get_sensitization_events_for_patient(db, patient_id)
    return [SensitizationEventResponse.model_validate(event) for event in events]


@router.get("/{patient_id}/reports", response_model=list[MatchReportResponse])
async def get_patient_reports_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get match reports for a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)

    reports = await get_reports_for_patient(db, patient_id)
    return [MatchReportResponse.model_validate(report) for report in reports]


# ----------------------------------------------------------------------
# Internal helper
# ----------------------------------------------------------------------
async def _ensure_patient_exists(
    db: AsyncSession, patient_id: uuid.UUID, doctor_id: uuid.UUID
) -> None:
    """Raise 404 if patient doesn't exist or isn't owned by the doctor."""
    patient = await get_patient_by_id_for_doctor(db, patient_id, doctor_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

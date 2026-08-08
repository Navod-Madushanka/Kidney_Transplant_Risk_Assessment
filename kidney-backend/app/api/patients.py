# app/api/patients.py
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.enums import ReportFileCategory
from app.schemas.antibody_profile import AntibodyProfileEntry
from app.schemas.donor_search import DonorCandidateResponse
from app.schemas.hla_typing import HLATypingEntry
from app.schemas.match_report import MatchReportResponse
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate
from app.schemas.report_file import ReportFileResponse
from app.schemas.sensitization_event import (
    SensitizationEventEntry,
    SensitizationEventResponse,
)
from app.services.antibody_profile_service import (
    get_patient_antibody_profiles,
    replace_patient_antibody_profiles,
)
from app.services.audit_service import create_audit_log
from app.services.donor_search_service import search_compatible_donors
from app.services.hla_typing_service import (
    get_patient_hla_typing_entries,
    replace_patient_hla_typing,
)
from app.services.match_report_service import get_reports_for_patient
from app.services.patient_service import (
    create_patient,
    delete_patient,
    get_patient_by_id_for_doctor,
    get_patients_for_doctor,  # ← should now work
    update_patient_details,
)
from app.services.report_file_service import (
    absolute_path_for,
    create_patient_report_file,
    delete_patient_report_file,
    get_patient_report_file_by_id,
    list_patient_report_files,
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
    try:
        patient = await create_patient(db, current_doctor.id, payload)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a patient with this NIC number.",
        )
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


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient_endpoint(
    patient_id: uuid.UUID,
    payload: PatientUpdate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a patient's core demographic fields (name, DOB, NIC). Blood
    type and Rh factor are permanent once set — see PatientUpdate."""
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    try:
        patient = await update_patient_details(db, patient, payload)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a patient with this NIC number.",
        )

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="updated_patient_details",
        patient_id=patient_id,
        details={
            "full_name": patient.full_name,
            "date_of_birth": patient.date_of_birth.isoformat(),
            "nic_number": patient.nic_number,
        },
    )

    return PatientResponse.model_validate(patient)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a patient: hides them from lists while keeping the
    record (and its HLA typings, report files, match reports) for audit
    history. Requires a valid doctor JWT — enforced by get_current_user,
    same as every other patient endpoint."""
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    await delete_patient(db, patient)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="deleted_patient",
        patient_id=patient_id,
        details={
            "full_name": patient.full_name,
            "nic_number": patient.nic_number,
        },
    )


@router.put("/{patient_id}/hla-typings", status_code=status.HTTP_204_NO_CONTENT)
async def replace_patient_hla_typing_endpoint(
    patient_id: uuid.UUID,
    entries: list[HLATypingEntry],
    ocr_verified: bool | None = None,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace HLA typing data for a patient. ocr_verified is set by the
    compatibility-check wizard when this data came from OCR extraction:
    True once a doctor has confirmed it against the source document, False
    if not yet confirmed (blocks POST /compatibility/check — see that
    endpoint's precondition check in app/api/compatibility.py). Omitted
    entirely by every other caller (e.g. manual edits via the patient
    detail page), which always counts as trusted."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)
    await replace_patient_hla_typing(db, patient_id, entries, ocr_verified=ocr_verified)


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
    ocr_verified: bool | None = None,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace antibody profile data for a patient. See ocr_verified's
    docstring on replace_patient_hla_typing_endpoint above — same contract."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)
    await replace_patient_antibody_profiles(db, patient_id, entries, ocr_verified=ocr_verified)


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


@router.get("/{patient_id}/compatible-donors", response_model=list[DonorCandidateResponse])
async def search_compatible_donors_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search the system-wide pool of AVAILABLE donors (registered by any
    other doctor) for ABO+HLA-mismatch compatibility with this patient. See
    app/services/donor_search_service.py for the prescreen logic.
    """
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    candidates = await search_compatible_donors(db, patient, current_doctor.id)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="searched_cross_hospital_donors",
        patient_id=patient_id,
        details={"result_count": len(candidates)},
    )

    return [
        DonorCandidateResponse(
            donor_id=candidate.donor.id,
            hospital_name=candidate.hospital_name,
            doctor_full_name=candidate.doctor_full_name,
            doctor_email=candidate.doctor_email,
            blood_type=candidate.donor.blood_type,
            rh_factor=candidate.donor.rh_factor,
            status=candidate.donor.status,
            abo_result=asdict(candidate.abo_result),
            mismatch_result=asdict(candidate.mismatch_result),
        )
        for candidate in candidates
    ]


@router.post(
    "/{patient_id}/report-files",
    response_model=ReportFileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_patient_report_file_endpoint(
    patient_id: uuid.UUID,
    category: ReportFileCategory = Form(...),
    file: UploadFile = File(...),
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach a report file (lab document/image) to a patient for reference.
    Purely storage — no data extraction. See app/services/report_file_service.py.
    """
    await _ensure_patient_exists(db, patient_id, current_doctor.id)

    report_file = await create_patient_report_file(db, patient_id, category, file)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="uploaded_patient_report_file",
        patient_id=patient_id,
        details={
            "report_file_id": str(report_file.id),
            "category": report_file.category.value,
            "original_filename": report_file.original_filename,
            "size_bytes": report_file.size_bytes,
        },
    )

    return ReportFileResponse.model_validate(report_file)


@router.get("/{patient_id}/report-files", response_model=list[ReportFileResponse])
async def list_patient_report_files_endpoint(
    patient_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List report files attached to a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)
    report_files = await list_patient_report_files(db, patient_id)
    return [ReportFileResponse.model_validate(rf) for rf in report_files]


@router.get("/{patient_id}/report-files/{report_file_id}/download")
async def download_patient_report_file_endpoint(
    patient_id: uuid.UUID,
    report_file_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download the original bytes of a report file attached to a patient."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)

    report_file = await get_patient_report_file_by_id(db, patient_id, report_file_id)
    if report_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file not found",
        )

    return FileResponse(
        absolute_path_for(report_file),
        media_type=report_file.content_type,
        filename=report_file.original_filename,
    )


@router.delete(
    "/{patient_id}/report-files/{report_file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_patient_report_file_endpoint(
    patient_id: uuid.UUID,
    report_file_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a report file attached to a patient (both the DB row and the
    file on disk). Not idempotent — deleting an already-deleted file 404s."""
    await _ensure_patient_exists(db, patient_id, current_doctor.id)

    deleted = await delete_patient_report_file(db, patient_id, report_file_id)
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file not found",
        )

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="deleted_patient_report_file",
        patient_id=patient_id,
        details={
            "report_file_id": str(report_file_id),
            "category": deleted.category.value,
            "original_filename": deleted.original_filename,
        },
    )


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

# app/api/donors.py
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.enums import ReportFileCategory
from app.schemas.donor import DonorCreate, DonorResponse, DonorStatusUpdate, DonorUpdate
from app.schemas.hla_typing import HLATypingEntry
from app.schemas.report_file import ReportFileResponse
from app.services.audit_service import create_audit_log
from app.services.donor_service import (
    create_donor,
    delete_donor,
    get_donor_by_id_for_doctor,
    get_donors_for_doctor,
    update_donor_details,
    update_donor_status,
)
from app.services.hla_typing_service import get_donor_hla_typings, replace_donor_hla_typing
from app.services.report_file_service import (
    absolute_path_for,
    create_donor_report_file,
    delete_donor_report_file,
    get_donor_report_file_by_id,
    list_donor_report_files,
)

router = APIRouter(prefix="/donors", tags=["donors"])


@router.get("", response_model=list[DonorResponse])
async def list_donors_endpoint(
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all donors belonging to the current doctor."""
    donors = await get_donors_for_doctor(db, current_doctor.id)
    return [DonorResponse.model_validate(d) for d in donors]


@router.post("", response_model=DonorResponse, status_code=status.HTTP_201_CREATED)
async def create_donor_endpoint(
    payload: DonorCreate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        donor = await create_donor(db, current_doctor.id, payload)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A donor with this NIC number is already registered in the "
                "system (donors are shared system-wide, unlike patients)."
            ),
        )
    return DonorResponse.model_validate(donor)


@router.get("/{donor_id}", response_model=DonorResponse)
async def get_donor_endpoint(
    donor_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    donor = await get_donor_by_id_for_doctor(db, donor_id, current_doctor.id)

    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    return DonorResponse.model_validate(donor)


@router.put("/{donor_id}", response_model=DonorResponse)
async def update_donor_endpoint(
    donor_id: uuid.UUID,
    payload: DonorUpdate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a donor's core demographic fields (name, DOB, NIC) and
    clinical suitability fields (eGFR, BP, BMI, diabetes, smoking). Blood
    type and Rh factor are permanent once set — see DonorUpdate."""
    donor = await get_donor_by_id_for_doctor(db, donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    try:
        donor = await update_donor_details(db, donor, payload)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A donor with this NIC number is already registered in the "
                "system (donors are shared system-wide, unlike patients)."
            ),
        )

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="updated_donor_details",
        donor_id=donor_id,
        details={
            "full_name": donor.full_name,
            "date_of_birth": donor.date_of_birth.isoformat(),
            "nic_number": donor.nic_number,
        },
    )

    return DonorResponse.model_validate(donor)


@router.delete("/{donor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_donor_endpoint(
    donor_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a donor: hides it from lists and cross-hospital search
    while keeping the record (and its HLA typings, report files, match
    reports) for audit history. Requires a valid doctor JWT — enforced by
    get_current_user, same as every other donor endpoint."""
    donor = await get_donor_by_id_for_doctor(db, donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    await delete_donor(db, donor)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="deleted_donor",
        donor_id=donor_id,
        details={
            "full_name": donor.full_name,
            "nic_number": donor.nic_number,
        },
    )


@router.put("/{donor_id}/status", response_model=DonorResponse)
async def update_donor_status_endpoint(
    donor_id: uuid.UUID,
    payload: DonorStatusUpdate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    donor = await get_donor_by_id_for_doctor(db, donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    donor = await update_donor_status(db, donor, payload.status)
    return DonorResponse.model_validate(donor)


@router.put("/{donor_id}/hla-typings", status_code=status.HTTP_204_NO_CONTENT)
async def replace_donor_hla_typing_endpoint(
    donor_id: uuid.UUID,
    entries: list[HLATypingEntry],
    ocr_verified: bool | None = None,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """See ocr_verified's docstring on replace_patient_hla_typing_endpoint
    in app/api/patients.py — same contract."""
    await _ensure_donor_exists(db, donor_id, current_doctor.id)
    await replace_donor_hla_typing(db, donor_id, entries, ocr_verified=ocr_verified)


@router.get("/{donor_id}/hla-typings", response_model=list[HLATypingEntry])
async def get_donor_hla_typings_endpoint(
    donor_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_donor_exists(db, donor_id, current_doctor.id)
    return await get_donor_hla_typings(db, donor_id)


@router.post(
    "/{donor_id}/report-files",
    response_model=ReportFileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_donor_report_file_endpoint(
    donor_id: uuid.UUID,
    category: ReportFileCategory = Form(...),
    file: UploadFile = File(...),
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach a report file (lab document/image) to a donor for reference.
    Purely storage — no data extraction. See app/services/report_file_service.py.
    """
    await _ensure_donor_exists(db, donor_id, current_doctor.id)

    report_file = await create_donor_report_file(db, donor_id, category, file)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="uploaded_donor_report_file",
        donor_id=donor_id,
        details={
            "report_file_id": str(report_file.id),
            "category": report_file.category.value,
            "original_filename": report_file.original_filename,
            "size_bytes": report_file.size_bytes,
        },
    )

    return ReportFileResponse.model_validate(report_file)


@router.get("/{donor_id}/report-files", response_model=list[ReportFileResponse])
async def list_donor_report_files_endpoint(
    donor_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List report files attached to a donor."""
    await _ensure_donor_exists(db, donor_id, current_doctor.id)
    report_files = await list_donor_report_files(db, donor_id)
    return [ReportFileResponse.model_validate(rf) for rf in report_files]


@router.get("/{donor_id}/report-files/{report_file_id}/download")
async def download_donor_report_file_endpoint(
    donor_id: uuid.UUID,
    report_file_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download the original bytes of a report file attached to a donor."""
    await _ensure_donor_exists(db, donor_id, current_doctor.id)

    report_file = await get_donor_report_file_by_id(db, donor_id, report_file_id)
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
    "/{donor_id}/report-files/{report_file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_donor_report_file_endpoint(
    donor_id: uuid.UUID,
    report_file_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a report file attached to a donor (both the DB row and the
    file on disk). Not idempotent — deleting an already-deleted file 404s."""
    await _ensure_donor_exists(db, donor_id, current_doctor.id)

    deleted = await delete_donor_report_file(db, donor_id, report_file_id)
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file not found",
        )

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="deleted_donor_report_file",
        donor_id=donor_id,
        details={
            "report_file_id": str(report_file_id),
            "category": deleted.category.value,
            "original_filename": deleted.original_filename,
        },
    )


# ----------------------------------------------------------------------
# Internal helper
# ----------------------------------------------------------------------
async def _ensure_donor_exists(
    db: AsyncSession, donor_id: uuid.UUID, doctor_id: uuid.UUID
) -> None:
    """Raise 404 if donor doesn't exist or isn't owned by the doctor."""
    donor = await get_donor_by_id_for_doctor(db, donor_id, doctor_id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

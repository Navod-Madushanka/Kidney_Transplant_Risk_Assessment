# app/api/donors.py
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.donor import Donor
from app.models.enums import ReportFileCategory
from app.schemas.donor import DonorCreate, DonorResponse, DonorStatusUpdate, DonorUpdate
from app.schemas.donor_risk import DonorRiskAssessmentResponse
from app.schemas.hla_typing import HLATypingEntry
from app.schemas.report_file import ReportFileResponse
from app.services.audit_service import create_audit_log
from app.services.donor_risk_service import (
    DonorRiskAssessmentInput,
    assess_donor_risk,
    calculate_age_years,
)
from app.services.donor_service import (
    IllegalDonorStatusTransition,
    create_donor,
    delete_donor,
    get_donor_by_id_for_doctor,
    get_donors_for_doctor,
    update_donor_details,
    update_donor_status,
)
from app.services.hla_typing_service import get_donor_hla_typings, replace_donor_hla_typing
from app.services.patient_service import get_patient_by_id_for_doctor
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
    await _ensure_intended_recipient_valid(db, payload.intended_recipient_id, current_doctor.id)

    try:
        donor = await create_donor(db, current_doctor.id, payload, commit=False)
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
        action="created_donor",
        donor_id=donor.id,
        details={
            "full_name": donor.full_name,
            "nic_number": donor.nic_number,
        },
        commit=False,
    )
    await db.commit()

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


@router.get("/{donor_id}/risk-assessment", response_model=DonorRiskAssessmentResponse)
async def get_donor_risk_assessment_endpoint(
    donor_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Donor safety assessment -- 'is it safe for this donor to donate?',
    independent of any recipient. Computed fresh on every call (like
    /exchange/match, nothing is persisted): see
    app/services/donor_risk_service.py for the model and its citation."""
    donor = await get_donor_by_id_for_doctor(db, donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    result = assess_donor_risk(_build_donor_risk_input(donor))
    return DonorRiskAssessmentResponse(**asdict(result))


@router.put("/{donor_id}", response_model=DonorResponse)
async def update_donor_endpoint(
    donor_id: uuid.UUID,
    payload: DonorUpdate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a donor's core demographic fields (name, DOB, NIC) and
    clinical/risk-assessment fields (eGFR, BP, BMI, diabetes, smoking status,
    sex, race, creatinine, urine ACR, antihypertensive medication use,
    family history). Blood type and Rh factor are permanent once set — see
    DonorUpdate."""
    donor = await get_donor_by_id_for_doctor(db, donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    await _ensure_intended_recipient_valid(db, payload.intended_recipient_id, current_doctor.id)

    try:
        donor = await update_donor_details(db, donor, payload, commit=False)
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
        commit=False,
    )
    await db.commit()

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

    await delete_donor(db, donor, commit=False)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="deleted_donor",
        donor_id=donor_id,
        details={
            "full_name": donor.full_name,
            "nic_number": donor.nic_number,
        },
        commit=False,
    )
    await db.commit()


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

    previous_status = donor.status
    try:
        donor = await update_donor_status(db, donor, payload.status, commit=False)
    except IllegalDonorStatusTransition as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="updated_donor_status",
        donor_id=donor_id,
        details={
            "previous_status": previous_status.value,
            "new_status": donor.status.value,
        },
        commit=False,
    )
    await db.commit()

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
    await replace_donor_hla_typing(
        db, donor_id, entries, ocr_verified=ocr_verified, doctor_id=current_doctor.id
    )


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

    report_file = await create_donor_report_file(db, donor_id, category, file, commit=False)

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
        commit=False,
    )
    await db.commit()

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

    deleted = await delete_donor_report_file(db, donor_id, report_file_id, commit=False)
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
        commit=False,
    )
    await db.commit()


# ----------------------------------------------------------------------
# Internal helpers
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


def _build_donor_risk_input(donor: Donor) -> DonorRiskAssessmentInput:
    """Adapts a Donor ORM row into donor_risk_service's plain input
    dataclass -- enum columns become their .value string (matching
    match_pipeline.py's convention), age is derived from date_of_birth.
    Numeric(...) columns come back from SQLAlchemy as decimal.Decimal, not
    float -- DonorResponse gets a free Decimal->float coercion from
    Pydantic's validation, but this dataclass has none, so it's done
    explicitly here (mixing Decimal and float in donor_risk_service's
    arithmetic raises TypeError otherwise)."""
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


async def _ensure_intended_recipient_valid(
    db: AsyncSession, intended_recipient_id: uuid.UUID | None, doctor_id: uuid.UUID
) -> None:
    """Raise 404 if an intended_recipient_id is set but isn't one of the
    calling doctor's own patients -- a donor can't be committed to a
    patient the registering doctor can't see (patients are doctor-isolated,
    unlike donors)."""
    if intended_recipient_id is None:
        return
    recipient = await get_patient_by_id_for_doctor(db, intended_recipient_id, doctor_id)
    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intended recipient not found",
        )

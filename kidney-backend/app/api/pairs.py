# app/api/pairs.py
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.donor_patient_pair import DonorPatientPair
from app.models.enums import ReportFileCategory
from app.schemas.donor import DonorResponse
from app.schemas.pair import PairDetailResponse, PairRegistrationRequest, PairResponse
from app.schemas.patient import PatientResponse
from app.schemas.report_file import ReportFileResponse
from app.services.audit_service import create_audit_log
from app.services.donor_service import create_donor, get_donor_by_id_for_doctor
from app.services.hla_typing_service import replace_donor_hla_typing, replace_patient_hla_typing
from app.services.pair_service import (
    IntendedRecipientMismatch,
    create_pair,
    get_pair_by_id_for_doctor,
    list_pairs_for_doctor,
)
from app.services.patient_service import create_patient, get_patient_by_id_for_doctor
from app.services.report_file_service import (
    absolute_path_for,
    create_pair_report_file,
    delete_pair_report_file,
    get_pair_report_file_by_id,
    list_pair_report_files,
)

router = APIRouter(prefix="/pairs", tags=["pairs"])


@router.post("", response_model=PairDetailResponse, status_code=status.HTTP_201_CREATED)
async def register_pair_endpoint(
    payload: PairRegistrationRequest,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a patient and donor together, plus the pair record linking
    them and (optionally) the crossmatch transcription -- see
    implementation-prompt-part-f.md F4.1. One transaction: a NIC conflict
    on either side rolls the whole thing back, half a pair is worse than
    none."""
    details_verified = payload.ocr_verified.details if payload.ocr_verified else None
    hla_verified = payload.ocr_verified.hla_typing if payload.ocr_verified else None

    patient_payload = payload.patient.model_copy(update={"details_verified": details_verified})
    try:
        patient = await create_patient(db, current_doctor.id, patient_payload, commit=False)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a patient with this NIC number.",
        )

    # intended_recipient_id is forced to the patient just created --
    # overrides whatever the client sent, since establishing this link is
    # the whole point of this endpoint. See DonorPatientPair's docstring
    # for why intended_recipient_id (not this pair row) stays authoritative
    # for the matching engine.
    donor_payload = payload.donor.model_copy(
        update={"details_verified": details_verified, "intended_recipient_id": patient.id}
    )
    try:
        donor = await create_donor(db, current_doctor.id, donor_payload, commit=False)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A donor with this NIC number is already registered in the "
                "system (donors are shared system-wide, unlike patients)."
            ),
        )

    crossmatch_verified = True if details_verified is None else details_verified
    try:
        pair = await create_pair(
            db,
            current_doctor.id,
            patient.id,
            donor.id,
            payload.crossmatch,
            crossmatch_verified,
            commit=False,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active pair already exists for this patient and donor.",
        )

    # doctor_id=None on both calls below is load-bearing: it skips the
    # per-typing audit entry these functions write internally (see
    # hla_typing_service.replace_patient_hla_typing's docstring), so
    # registration produces exactly the one "registered_pair" audit row
    # below rather than three.
    await replace_patient_hla_typing(
        db, patient.id, payload.patient_hla, ocr_verified=hla_verified, doctor_id=None, commit=False
    )
    await replace_donor_hla_typing(
        db, donor.id, payload.donor_hla, ocr_verified=hla_verified, doctor_id=None, commit=False
    )

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="registered_pair",
        patient_id=patient.id,
        donor_id=donor.id,
        details={
            "pair_id": str(pair.id),
            "entry_source": "ocr" if payload.ocr_verified else "manual",
        },
        commit=False,
    )
    await db.commit()

    # Re-fetch rather than reuse the in-memory patient/donor objects: the
    # HLA-typing replace calls above run a bulk UPDATE against
    # Patient.updated_at/Donor.updated_at (onupdate=func.now(), a
    # server-side default the ORM can't evaluate client-side), which
    # expires those attributes on the in-session objects -- accessing them
    # via a plain sync getattr (as PatientResponse.model_validate below
    # would) triggers an implicit async lazy-load with no greenlet context.
    patient = await get_patient_by_id_for_doctor(db, patient.id, current_doctor.id)
    donor = await get_donor_by_id_for_doctor(db, donor.id, current_doctor.id)

    return PairDetailResponse(
        **PairResponse.model_validate(pair).model_dump(),
        patient=PatientResponse.model_validate(patient),
        donor=DonorResponse.model_validate(donor),
    )


@router.get("", response_model=list[PairResponse])
async def list_pairs_endpoint(
    patient_id: uuid.UUID | None = Query(default=None),
    donor_id: uuid.UUID | None = Query(default=None),
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pairs = await list_pairs_for_doctor(db, current_doctor.id, patient_id=patient_id, donor_id=donor_id)
    return [PairResponse.model_validate(p) for p in pairs]


@router.get("/{pair_id}", response_model=PairDetailResponse)
async def get_pair_endpoint(
    pair_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pair = await _get_pair_or_error(db, pair_id, current_doctor.id)
    patient = await get_patient_by_id_for_doctor(db, pair.patient_id, current_doctor.id)
    donor = await get_donor_by_id_for_doctor(db, pair.donor_id, current_doctor.id)

    return PairDetailResponse(
        **PairResponse.model_validate(pair).model_dump(),
        patient=PatientResponse.model_validate(patient),
        donor=DonorResponse.model_validate(donor),
    )


@router.post(
    "/{pair_id}/report-files",
    response_model=ReportFileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_pair_report_file_endpoint(
    pair_id: uuid.UUID,
    category: ReportFileCategory = Form(...),
    file: UploadFile = File(...),
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach a report file (HLA typing / crossmatch report) to a pair.
    Purely storage — no data extraction. See app/services/report_file_service.py."""
    pair = await _get_pair_or_error(db, pair_id, current_doctor.id)

    report_file = await create_pair_report_file(db, pair_id, category, file, commit=False)

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="uploaded_pair_report_file",
        patient_id=pair.patient_id,
        donor_id=pair.donor_id,
        details={
            "pair_id": str(pair_id),
            "report_file_id": str(report_file.id),
            "category": report_file.category.value,
            "original_filename": report_file.original_filename,
            "size_bytes": report_file.size_bytes,
        },
        commit=False,
    )
    await db.commit()

    return ReportFileResponse.model_validate(report_file)


@router.get("/{pair_id}/report-files", response_model=list[ReportFileResponse])
async def list_pair_report_files_endpoint(
    pair_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_pair_or_error(db, pair_id, current_doctor.id)
    report_files = await list_pair_report_files(db, pair_id)
    return [ReportFileResponse.model_validate(rf) for rf in report_files]


@router.get("/{pair_id}/report-files/{report_file_id}/download")
async def download_pair_report_file_endpoint(
    pair_id: uuid.UUID,
    report_file_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_pair_or_error(db, pair_id, current_doctor.id)

    report_file = await get_pair_report_file_by_id(db, pair_id, report_file_id)
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


@router.delete("/{pair_id}/report-files/{report_file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pair_report_file_endpoint(
    pair_id: uuid.UUID,
    report_file_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pair = await _get_pair_or_error(db, pair_id, current_doctor.id)

    deleted = await delete_pair_report_file(db, pair_id, report_file_id, commit=False)
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file not found",
        )

    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="deleted_pair_report_file",
        patient_id=pair.patient_id,
        donor_id=pair.donor_id,
        details={
            "pair_id": str(pair_id),
            "report_file_id": str(report_file_id),
            "category": deleted.category.value,
            "original_filename": deleted.original_filename,
        },
        commit=False,
    )
    await db.commit()


# ----------------------------------------------------------------------
# Internal helper
# ----------------------------------------------------------------------
async def _get_pair_or_error(
    db: AsyncSession, pair_id: uuid.UUID, doctor_id: uuid.UUID
) -> DonorPatientPair:
    """Raise 404 if the pair doesn't exist or isn't owned by the doctor;
    409 if it exists but has drifted from its donor's intended_recipient_id
    (see IntendedRecipientMismatch)."""
    try:
        pair = await get_pair_by_id_for_doctor(db, pair_id, doctor_id)
    except IntendedRecipientMismatch as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pair not found")
    return pair

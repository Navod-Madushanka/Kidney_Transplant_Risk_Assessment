# app/services/report_file_service.py
"""
Storage + CRUD for report files attached to patient/donor records — plain
reference documents (lab reports, charts) for a doctor to upload/download/
delete later. Deliberately separate from the OCR pipeline (app/api/ocr.py):
nothing here extracts data from the file, it's just persisted bytes plus
metadata.

Files live on local disk under settings.report_files_storage_dir. The
on-disk filename is always server-generated (a fresh uuid4, extension from
the validated content-type) — never derived from the client-supplied
filename, which is stored purely as display metadata (original_filename)
and never touches the filesystem. This rules out path traversal and
collisions by construction.
"""
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.donor_report_file import DonorReportFile
from app.models.enums import ReportFileCategory
from app.models.patient_report_file import PatientReportFile

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


@dataclass
class DeletedReportFileInfo:
    category: ReportFileCategory
    original_filename: str


def _upload_root() -> Path:
    return Path(get_settings().report_files_storage_dir)


def _validate_content_type(content_type: str | None) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type}. Only PDF, JPG, and PNG are accepted.",
        )


def _build_storage_path(kind: str, entity_id: uuid.UUID, content_type: str) -> Path:
    ext = ALLOWED_CONTENT_TYPES[content_type]
    return Path(kind) / str(entity_id) / f"{uuid.uuid4().hex}{ext}"


async def _save_upload(file: UploadFile, relative_path: Path) -> int:
    settings = get_settings()
    max_size_bytes = settings.report_files_max_size_mb * 1024 * 1024
    absolute_path = _upload_root() / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    try:
        with absolute_path.open("wb") as out:
            while chunk := await file.read(_CHUNK_SIZE):
                size += len(chunk)
                if size > max_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File exceeds the {settings.report_files_max_size_mb}MB limit.",
                    )
                out.write(chunk)
    except HTTPException:
        absolute_path.unlink(missing_ok=True)
        raise

    return size


def _delete_from_disk(relative_path: str) -> None:
    (_upload_root() / relative_path).unlink(missing_ok=True)


def absolute_path_for(report_file: PatientReportFile | DonorReportFile) -> Path:
    return _upload_root() / report_file.storage_path


async def create_patient_report_file(
    db: AsyncSession, patient_id: uuid.UUID, category: ReportFileCategory, file: UploadFile
) -> PatientReportFile:
    _validate_content_type(file.content_type)
    relative_path = _build_storage_path("patients", patient_id, file.content_type)
    size = await _save_upload(file, relative_path)

    report_file = PatientReportFile(
        patient_id=patient_id,
        category=category,
        original_filename=file.filename or "upload",
        storage_path=str(relative_path),
        content_type=file.content_type,
        size_bytes=size,
    )
    db.add(report_file)
    await db.commit()
    await db.refresh(report_file)
    return report_file


async def list_patient_report_files(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[PatientReportFile]:
    result = await db.execute(
        select(PatientReportFile)
        .where(PatientReportFile.patient_id == patient_id)
        .order_by(PatientReportFile.created_at.desc())
    )
    return list(result.scalars().all())


async def get_patient_report_file_by_id(
    db: AsyncSession, patient_id: uuid.UUID, report_file_id: uuid.UUID
) -> PatientReportFile | None:
    result = await db.execute(
        select(PatientReportFile).where(
            PatientReportFile.id == report_file_id,
            PatientReportFile.patient_id == patient_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_patient_report_file(
    db: AsyncSession, patient_id: uuid.UUID, report_file_id: uuid.UUID
) -> DeletedReportFileInfo | None:
    report_file = await get_patient_report_file_by_id(db, patient_id, report_file_id)
    if report_file is None:
        return None

    storage_path = report_file.storage_path
    info = DeletedReportFileInfo(
        category=report_file.category, original_filename=report_file.original_filename
    )

    await db.execute(delete(PatientReportFile).where(PatientReportFile.id == report_file_id))
    await db.commit()
    _delete_from_disk(storage_path)
    return info


async def create_donor_report_file(
    db: AsyncSession, donor_id: uuid.UUID, category: ReportFileCategory, file: UploadFile
) -> DonorReportFile:
    _validate_content_type(file.content_type)
    relative_path = _build_storage_path("donors", donor_id, file.content_type)
    size = await _save_upload(file, relative_path)

    report_file = DonorReportFile(
        donor_id=donor_id,
        category=category,
        original_filename=file.filename or "upload",
        storage_path=str(relative_path),
        content_type=file.content_type,
        size_bytes=size,
    )
    db.add(report_file)
    await db.commit()
    await db.refresh(report_file)
    return report_file


async def list_donor_report_files(db: AsyncSession, donor_id: uuid.UUID) -> list[DonorReportFile]:
    result = await db.execute(
        select(DonorReportFile)
        .where(DonorReportFile.donor_id == donor_id)
        .order_by(DonorReportFile.created_at.desc())
    )
    return list(result.scalars().all())


async def get_donor_report_file_by_id(
    db: AsyncSession, donor_id: uuid.UUID, report_file_id: uuid.UUID
) -> DonorReportFile | None:
    result = await db.execute(
        select(DonorReportFile).where(
            DonorReportFile.id == report_file_id,
            DonorReportFile.donor_id == donor_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_donor_report_file(
    db: AsyncSession, donor_id: uuid.UUID, report_file_id: uuid.UUID
) -> DeletedReportFileInfo | None:
    report_file = await get_donor_report_file_by_id(db, donor_id, report_file_id)
    if report_file is None:
        return None

    storage_path = report_file.storage_path
    info = DeletedReportFileInfo(
        category=report_file.category, original_filename=report_file.original_filename
    )

    await db.execute(delete(DonorReportFile).where(DonorReportFile.id == report_file_id))
    await db.commit()
    _delete_from_disk(storage_path)
    return info

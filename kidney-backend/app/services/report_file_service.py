# app/services/report_file_service.py
"""
Storage + CRUD for report files attached to patient/donor/pair records —
plain reference documents (lab reports, charts) for a doctor to upload/
download/delete later. Deliberately separate from the OCR pipeline
(app/api/ocr.py): nothing here extracts data from the file, it's just
persisted bytes plus metadata.

Files live on local disk under settings.report_files_storage_dir. The
on-disk filename is always server-generated (a fresh uuid4, extension from
the validated content-type) — never derived from the client-supplied
filename, which is stored purely as display metadata (original_filename)
and never touches the filesystem. This rules out path traversal and
collisions by construction.

The patient/donor/pair CRUD below is one owner-parameterized implementation
(_create_report_file/_list_report_files/_get_report_file_by_id/
_delete_report_file) behind thin per-owner wrappers that keep their existing
names and signatures, so call sites elsewhere don't change.
"""
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.donor_report_file import DonorReportFile
from app.models.enums import PAIR_REPORT_CATEGORIES, PATIENT_REPORT_CATEGORIES, ReportFileCategory
from app.models.pair_report_file import PairReportFile
from app.models.patient_report_file import PatientReportFile

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

_CHUNK_SIZE = 1024 * 1024  # 1 MiB

ReportFileModel = Any  # PatientReportFile | DonorReportFile | PairReportFile


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


def absolute_path_for(report_file: ReportFileModel) -> Path:
    return _upload_root() / report_file.storage_path


async def _create_report_file(
    db: AsyncSession,
    model: type[ReportFileModel],
    owner_field: str,
    owner_id: uuid.UUID,
    kind: str,
    category: ReportFileCategory,
    file: UploadFile,
    commit: bool = True,
    allowed_categories: frozenset[ReportFileCategory] | None = None,
) -> ReportFileModel:
    """Create (or replace) the report file for this owner's category slot.

    Each category is a dedicated, nullable slot rather than an open-ended
    list — re-uploading to a filled slot replaces the previous file, both
    the DB row and the bytes on disk.

    allowed_categories=None means unrestricted (every ReportFileCategory
    value accepted) -- used for the donor endpoint, which this codebase's
    pair-registration feature deliberately leaves unrestricted at the API
    layer since nothing in the UI can reach it anymore. Patient/pair
    endpoints pass PATIENT_REPORT_CATEGORIES/PAIR_REPORT_CATEGORIES.
    """
    if allowed_categories is not None and category not in allowed_categories:
        allowed = ", ".join(sorted(c.value for c in allowed_categories))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Category '{category.value}' is not valid here. Allowed: {allowed}.",
        )

    _validate_content_type(file.content_type)

    existing = await db.execute(
        select(model).where(
            getattr(model, owner_field) == owner_id,
            model.category == category,
        )
    )
    existing_report_file = existing.scalar_one_or_none()

    relative_path = _build_storage_path(kind, owner_id, file.content_type)
    size = await _save_upload(file, relative_path)

    if existing_report_file is not None:
        old_storage_path = existing_report_file.storage_path
        await db.execute(delete(model).where(model.id == existing_report_file.id))
        _delete_from_disk(old_storage_path)

    report_file = model(
        **{owner_field: owner_id},
        category=category,
        original_filename=file.filename or "upload",
        storage_path=str(relative_path),
        content_type=file.content_type,
        size_bytes=size,
    )
    db.add(report_file)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(report_file)
    return report_file


async def _list_report_files(
    db: AsyncSession, model: type[ReportFileModel], owner_field: str, owner_id: uuid.UUID
) -> list[ReportFileModel]:
    result = await db.execute(
        select(model)
        .where(getattr(model, owner_field) == owner_id)
        .order_by(model.created_at.desc())
    )
    return list(result.scalars().all())


async def _get_report_file_by_id(
    db: AsyncSession,
    model: type[ReportFileModel],
    owner_field: str,
    owner_id: uuid.UUID,
    report_file_id: uuid.UUID,
) -> ReportFileModel | None:
    result = await db.execute(
        select(model).where(
            model.id == report_file_id,
            getattr(model, owner_field) == owner_id,
        )
    )
    return result.scalar_one_or_none()


async def _delete_report_file(
    db: AsyncSession,
    model: type[ReportFileModel],
    owner_field: str,
    owner_id: uuid.UUID,
    report_file_id: uuid.UUID,
    commit: bool = True,
) -> DeletedReportFileInfo | None:
    report_file = await _get_report_file_by_id(db, model, owner_field, owner_id, report_file_id)
    if report_file is None:
        return None

    storage_path = report_file.storage_path
    info = DeletedReportFileInfo(
        category=report_file.category, original_filename=report_file.original_filename
    )

    await db.execute(delete(model).where(model.id == report_file_id))
    await db.flush()
    if commit:
        await db.commit()
    _delete_from_disk(storage_path)
    return info


async def create_patient_report_file(
    db: AsyncSession,
    patient_id: uuid.UUID,
    category: ReportFileCategory,
    file: UploadFile,
    commit: bool = True,
) -> PatientReportFile:
    return await _create_report_file(
        db,
        PatientReportFile,
        "patient_id",
        patient_id,
        "patients",
        category,
        file,
        commit=commit,
        allowed_categories=PATIENT_REPORT_CATEGORIES,
    )


async def list_patient_report_files(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[PatientReportFile]:
    return await _list_report_files(db, PatientReportFile, "patient_id", patient_id)


async def get_patient_report_file_by_id(
    db: AsyncSession, patient_id: uuid.UUID, report_file_id: uuid.UUID
) -> PatientReportFile | None:
    return await _get_report_file_by_id(
        db, PatientReportFile, "patient_id", patient_id, report_file_id
    )


async def delete_patient_report_file(
    db: AsyncSession, patient_id: uuid.UUID, report_file_id: uuid.UUID, commit: bool = True
) -> DeletedReportFileInfo | None:
    return await _delete_report_file(
        db, PatientReportFile, "patient_id", patient_id, report_file_id, commit=commit
    )


async def create_donor_report_file(
    db: AsyncSession,
    donor_id: uuid.UUID,
    category: ReportFileCategory,
    file: UploadFile,
    commit: bool = True,
) -> DonorReportFile:
    return await _create_report_file(
        db, DonorReportFile, "donor_id", donor_id, "donors", category, file, commit=commit
    )


async def list_donor_report_files(db: AsyncSession, donor_id: uuid.UUID) -> list[DonorReportFile]:
    return await _list_report_files(db, DonorReportFile, "donor_id", donor_id)


async def get_donor_report_file_by_id(
    db: AsyncSession, donor_id: uuid.UUID, report_file_id: uuid.UUID
) -> DonorReportFile | None:
    return await _get_report_file_by_id(db, DonorReportFile, "donor_id", donor_id, report_file_id)


async def delete_donor_report_file(
    db: AsyncSession, donor_id: uuid.UUID, report_file_id: uuid.UUID, commit: bool = True
) -> DeletedReportFileInfo | None:
    return await _delete_report_file(
        db, DonorReportFile, "donor_id", donor_id, report_file_id, commit=commit
    )


async def create_pair_report_file(
    db: AsyncSession,
    pair_id: uuid.UUID,
    category: ReportFileCategory,
    file: UploadFile,
    commit: bool = True,
) -> PairReportFile:
    return await _create_report_file(
        db,
        PairReportFile,
        "pair_id",
        pair_id,
        "pairs",
        category,
        file,
        commit=commit,
        allowed_categories=PAIR_REPORT_CATEGORIES,
    )


async def list_pair_report_files(db: AsyncSession, pair_id: uuid.UUID) -> list[PairReportFile]:
    return await _list_report_files(db, PairReportFile, "pair_id", pair_id)


async def get_pair_report_file_by_id(
    db: AsyncSession, pair_id: uuid.UUID, report_file_id: uuid.UUID
) -> PairReportFile | None:
    return await _get_report_file_by_id(db, PairReportFile, "pair_id", pair_id, report_file_id)


async def delete_pair_report_file(
    db: AsyncSession, pair_id: uuid.UUID, report_file_id: uuid.UUID, commit: bool = True
) -> DeletedReportFileInfo | None:
    return await _delete_report_file(
        db, PairReportFile, "pair_id", pair_id, report_file_id, commit=commit
    )

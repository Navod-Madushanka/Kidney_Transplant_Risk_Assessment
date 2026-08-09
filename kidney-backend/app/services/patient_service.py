import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientUpdate


async def create_patient(
    db: AsyncSession, doctor_id: uuid.UUID, payload: PatientCreate, commit: bool = True
) -> Patient:
    """commit=False lets a caller fold this write into the same transaction
    as a paired create_audit_log call (see create_audit_log's docstring) so
    a crash between the two can't leave one without the other."""
    patient = Patient(
        doctor_id=doctor_id,
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth,
        blood_type=payload.blood_type,
        rh_factor=payload.rh_factor,
        nic_number=payload.nic_number,
        details_verified=True if payload.details_verified is None else payload.details_verified,
    )
    db.add(patient)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(patient)

    return patient


async def get_patient_by_id_for_doctor(
    db: AsyncSession, patient_id: uuid.UUID, doctor_id: uuid.UUID
) -> Patient | None:
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == doctor_id,
            Patient.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_patients_for_doctor(
    db: AsyncSession, doctor_id: uuid.UUID
) -> list[Patient]:
    result = await db.execute(
        select(Patient)
        .where(Patient.doctor_id == doctor_id, Patient.is_deleted.is_(False))
        .order_by(Patient.full_name)
    )
    return list(result.scalars().all())


async def delete_patient(db: AsyncSession, patient: Patient, commit: bool = True) -> Patient:
    """Soft-delete: hides the patient from lists/searches while keeping the
    row (and its HLA typings, report files, match reports) for audit
    history — hard-deleting would hit FK RESTRICT on any of those.
    commit=False — see create_patient's docstring."""
    patient.is_deleted = True
    patient.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(patient)
    return patient


async def update_patient_details(
    db: AsyncSession, patient: Patient, payload: PatientUpdate, commit: bool = True
) -> Patient:
    """commit=False — see create_patient's docstring."""
    patient.full_name = payload.full_name
    patient.date_of_birth = payload.date_of_birth
    patient.nic_number = payload.nic_number
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(patient)
    return patient

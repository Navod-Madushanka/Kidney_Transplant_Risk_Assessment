import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.schemas.patient import PatientCreate


async def create_patient(
    db: AsyncSession, doctor_id: uuid.UUID, payload: PatientCreate
) -> Patient:
    patient = Patient(
        doctor_id=doctor_id,
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth,
        blood_type=payload.blood_type,
        rh_factor=payload.rh_factor,
        nic_number=payload.nic_number,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    return patient


async def get_patient_by_id_for_doctor(
    db: AsyncSession, patient_id: uuid.UUID, doctor_id: uuid.UUID
) -> Patient | None:
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def get_patients_for_doctor(
    db: AsyncSession, doctor_id: uuid.UUID
) -> list[Patient]:
    result = await db.execute(
        select(Patient)
        .where(Patient.doctor_id == doctor_id)
        .order_by(Patient.full_name)
    )
    return list(result.scalars().all())
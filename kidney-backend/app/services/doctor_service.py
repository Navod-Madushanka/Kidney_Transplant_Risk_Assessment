# app/services/doctor_service.py
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.doctor import Doctor


async def get_doctor_by_email(db: AsyncSession, email: str) -> Doctor | None:
    result = await db.execute(select(Doctor).where(Doctor.email == email))
    return result.scalar_one_or_none()


async def get_doctor_by_id(db: AsyncSession, doctor_id: uuid.UUID) -> Doctor | None:
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    return result.scalar_one_or_none()


async def create_doctor(
    db: AsyncSession,
    hospital_id,
    email: str,
    password: str,
    full_name: str,
) -> Doctor:
    doctor = Doctor(
        hospital_id=hospital_id,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
    )
    db.add(doctor)
    await db.flush()

    return doctor
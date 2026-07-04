# app/services/doctor_service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor


async def get_doctor_by_email(db: AsyncSession, email: str) -> Doctor | None:
    result = await db.execute(select(Doctor).where(Doctor.email == email))
    return result.scalar_one_or_none()
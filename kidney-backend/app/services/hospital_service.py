# app/services/hospital_service.py
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hospital import Hospital


async def get_hospital_by_id(db: AsyncSession, hospital_id: uuid.UUID) -> Hospital | None:
    result = await db.execute(select(Hospital).where(Hospital.id == hospital_id))
    return result.scalar_one_or_none()


async def get_or_create_hospital(db: AsyncSession, name: str) -> Hospital:
    result = await db.execute(select(Hospital).where(Hospital.name == name))
    hospital = result.scalar_one_or_none()

    if hospital is not None:
        return hospital

    hospital = Hospital(name=name)
    db.add(hospital)
    await db.flush()

    return hospital

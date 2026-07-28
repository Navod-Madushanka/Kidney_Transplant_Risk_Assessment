# app/services/hospital_service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hospital import Hospital


async def get_or_create_hospital(db: AsyncSession, name: str) -> Hospital:
    result = await db.execute(select(Hospital).where(Hospital.name == name))
    hospital = result.scalar_one_or_none()

    if hospital is not None:
        return hospital

    hospital = Hospital(name=name)
    db.add(hospital)
    await db.flush()

    return hospital

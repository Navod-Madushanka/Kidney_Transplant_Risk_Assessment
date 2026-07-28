import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.schemas.donor import DonorCreate


async def create_donor(
    db: AsyncSession, doctor_id: uuid.UUID, payload: DonorCreate
) -> Donor:
    donor = Donor(
        doctor_id=doctor_id,
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth,
        blood_type=payload.blood_type,
        rh_factor=payload.rh_factor,
        nic_number=payload.nic_number,
    )
    db.add(donor)
    await db.commit()
    await db.refresh(donor)

    return donor


async def get_donor_by_id_for_doctor(
    db: AsyncSession, donor_id: uuid.UUID, doctor_id: uuid.UUID
) -> Donor | None:
    result = await db.execute(
        select(Donor).where(Donor.id == donor_id, Donor.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def get_donors_for_doctor(
    db: AsyncSession, doctor_id: uuid.UUID
) -> list[Donor]:
    result = await db.execute(
        select(Donor)
        .where(Donor.doctor_id == doctor_id)
        .order_by(Donor.full_name)
    )
    return list(result.scalars().all())
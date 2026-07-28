# app/services/antibody_profile_service.py
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.antibody_profile import AntibodyProfile
from app.schemas.antibody_profile import AntibodyProfileEntry


async def get_patient_antibody_profiles(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[AntibodyProfile]:
    result = await db.execute(
        select(AntibodyProfile).where(AntibodyProfile.patient_id == patient_id)
    )
    return list(result.scalars().all())


async def replace_patient_antibody_profiles(
    db: AsyncSession, patient_id: uuid.UUID, entries: list[AntibodyProfileEntry]
) -> None:
    await db.execute(
        delete(AntibodyProfile).where(AntibodyProfile.patient_id == patient_id)
    )

    for entry in entries:
        profile_row = AntibodyProfile(
            patient_id=patient_id,
            antigen=entry.antigen,
            mfi=entry.mfi,
        )
        db.add(profile_row)

    await db.commit()


async def get_patient_sensitized_antigens(
    db: AsyncSession, patient_id: uuid.UUID, mfi_cutoff_value: float
) -> list[str]:
    profiles = await get_patient_antibody_profiles(db, patient_id)
    return [
        profile.antigen for profile in profiles if float(profile.mfi) > mfi_cutoff_value
    ]

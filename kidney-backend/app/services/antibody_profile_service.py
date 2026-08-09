# app/services/antibody_profile_service.py
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.antibody_profile import AntibodyProfile
from app.models.patient import Patient
from app.schemas.antibody_profile import AntibodyProfileEntry
from app.services.audit_service import create_audit_log


async def get_patient_antibody_profiles(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[AntibodyProfile]:
    result = await db.execute(
        select(AntibodyProfile).where(AntibodyProfile.patient_id == patient_id)
    )
    return list(result.scalars().all())


async def replace_patient_antibody_profiles(
    db: AsyncSession,
    patient_id: uuid.UUID,
    entries: list[AntibodyProfileEntry],
    ocr_verified: bool | None = None,
    doctor_id: uuid.UUID | None = None,
) -> None:
    """None (no claim made about this write) preserves whatever
    antibody_profile_verified already was, rather than resetting it to
    trusted -- see hla_typing_service._resolve_verified's docstring, same
    bug (review #2 bug 5), same fix, same reasoning. doctor_id -- see
    hla_typing_service.replace_patient_hla_typing's docstring, same
    audit-attribution contract."""
    previous_verified = (
        await db.execute(select(Patient.antibody_profile_verified).where(Patient.id == patient_id))
    ).scalar_one()
    new_verified = previous_verified if ocr_verified is None else ocr_verified

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

    await db.execute(
        update(Patient)
        .where(Patient.id == patient_id)
        .values(antibody_profile_verified=new_verified)
    )

    if doctor_id is not None:
        await create_audit_log(
            db,
            doctor_id=doctor_id,
            action="replaced_patient_antibody_profiles",
            patient_id=patient_id,
            details={
                "entry_count": len(entries),
                "previous_verified": previous_verified,
                "new_verified": new_verified,
            },
            commit=False,
        )
    await db.commit()


async def get_patient_antibody_profiles_bulk(
    db: AsyncSession, patient_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[AntibodyProfile]]:
    """Same rows as get_patient_antibody_profiles but for many patients in
    one query, grouped by patient_id — mirrors hla_typing_service's donor/
    patient bulk fetchers. Used by exchange_graph_service to DSA-screen an
    entire exchange pool without one query per recipient.
    """
    if not patient_ids:
        return {}

    result = await db.execute(
        select(AntibodyProfile).where(AntibodyProfile.patient_id.in_(patient_ids))
    )
    profiles_by_patient: dict[uuid.UUID, list[AntibodyProfile]] = {}
    for row in result.scalars().all():
        profiles_by_patient.setdefault(row.patient_id, []).append(row)
    return profiles_by_patient


async def get_patient_sensitized_antigens(
    db: AsyncSession, patient_id: uuid.UUID, mfi_cutoff_value: float
) -> list[str]:
    profiles = await get_patient_antibody_profiles(db, patient_id)
    return [
        profile.antigen for profile in profiles if float(profile.mfi) > mfi_cutoff_value
    ]

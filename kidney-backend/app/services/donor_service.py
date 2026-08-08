import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.enums import DonorStatus
from app.schemas.donor import DonorCreate, DonorUpdate


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
        egfr=payload.egfr,
        systolic_bp=payload.systolic_bp,
        diastolic_bp=payload.diastolic_bp,
        bmi=payload.bmi,
        has_diabetes=payload.has_diabetes,
        is_smoker=payload.is_smoker,
    )
    db.add(donor)
    await db.commit()
    await db.refresh(donor)

    return donor


async def get_donor_by_id_for_doctor(
    db: AsyncSession, donor_id: uuid.UUID, doctor_id: uuid.UUID
) -> Donor | None:
    result = await db.execute(
        select(Donor).where(
            Donor.id == donor_id,
            Donor.doctor_id == doctor_id,
            Donor.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_donors_for_doctor(
    db: AsyncSession, doctor_id: uuid.UUID
) -> list[Donor]:
    result = await db.execute(
        select(Donor)
        .where(Donor.doctor_id == doctor_id, Donor.is_deleted.is_(False))
        .order_by(Donor.full_name)
    )
    return list(result.scalars().all())


async def delete_donor(db: AsyncSession, donor: Donor) -> Donor:
    """Soft-delete: hides the donor from lists/searches while keeping the
    row (and its HLA typings, report files, match reports) for audit
    history — hard-deleting would hit FK RESTRICT on any of those."""
    donor.is_deleted = True
    donor.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(donor)
    return donor


async def update_donor_status(
    db: AsyncSession, donor: Donor, status: DonorStatus
) -> Donor:
    donor.status = status
    await db.commit()
    await db.refresh(donor)
    return donor


async def update_donor_details(
    db: AsyncSession, donor: Donor, payload: DonorUpdate
) -> Donor:
    donor.full_name = payload.full_name
    donor.date_of_birth = payload.date_of_birth
    donor.nic_number = payload.nic_number
    donor.egfr = payload.egfr
    donor.systolic_bp = payload.systolic_bp
    donor.diastolic_bp = payload.diastolic_bp
    donor.bmi = payload.bmi
    donor.has_diabetes = payload.has_diabetes
    donor.is_smoker = payload.is_smoker
    await db.commit()
    await db.refresh(donor)
    return donor


async def get_donor_for_compatibility_check(
    db: AsyncSession, donor_id: uuid.UUID, doctor_id: uuid.UUID
) -> Donor | None:
    """Resolves a donor for POST /compatibility/check: the calling doctor's
    own donor (any status), OR a donor owned by a different doctor iff it's
    currently AVAILABLE. Deliberately separate from get_donor_by_id_for_doctor
    (which stays owner-only for CRUD/HLA-typing endpoints) so opening up
    cross-hospital checks can't accidentally loosen anything else. Reads
    status fresh rather than trusting an earlier search result, so a donor
    reserved between search and submission cleanly 404s here.
    """
    result = await db.execute(
        select(Donor).where(Donor.id == donor_id, Donor.is_deleted.is_(False))
    )
    donor = result.scalar_one_or_none()
    if donor is None:
        return None
    if donor.doctor_id == doctor_id or donor.status == DonorStatus.AVAILABLE:
        return donor
    return None

# app/services/pair_service.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.donor_patient_pair import DonorPatientPair
from app.schemas.pair import PairCrossmatchInput


class IntendedRecipientMismatch(Exception):
    """Raised when a pair's (patient_id, donor_id) no longer agrees with
    donor.intended_recipient_id -- see DonorPatientPair's docstring for why
    this can happen (PUT /donors/{id} can still repoint
    intended_recipient_id without going through this table) and why it's
    detected here rather than prevented at donor-write time."""

    def __init__(self, pair_id: uuid.UUID, donor_id: uuid.UUID):
        self.pair_id = pair_id
        self.donor_id = donor_id
        super().__init__(
            f"Pair {pair_id}'s donor {donor_id} no longer has this pair's patient as its "
            "intended_recipient_id -- the two have drifted apart."
        )


async def create_pair(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    patient_id: uuid.UUID,
    donor_id: uuid.UUID,
    crossmatch: PairCrossmatchInput | None,
    crossmatch_verified: bool,
    commit: bool = True,
) -> DonorPatientPair:
    """commit=False — see patient_service.create_patient's docstring; this
    is written to be folded into POST /pairs's single transaction alongside
    the patient/donor creates and HLA-typing replacements."""
    pair = DonorPatientPair(
        doctor_id=doctor_id,
        patient_id=patient_id,
        donor_id=donor_id,
        crossmatch_t_cell_result=crossmatch.t_cell_result if crossmatch else None,
        crossmatch_b_cell_result=crossmatch.b_cell_result if crossmatch else None,
        crossmatch_interpretation=crossmatch.interpretation if crossmatch else None,
        crossmatch_remarks=crossmatch.remarks if crossmatch else None,
        crossmatch_test_date=crossmatch.test_date if crossmatch else None,
        crossmatch_verified=crossmatch_verified,
    )
    db.add(pair)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(pair)
    return pair


async def get_pair_by_id_for_doctor(
    db: AsyncSession, pair_id: uuid.UUID, doctor_id: uuid.UUID
) -> DonorPatientPair | None:
    """Also enforces the intended_recipient_id consistency invariant (see
    IntendedRecipientMismatch) on every read, since it can't be enforced at
    donor-write time without touching donors.py -- see DonorPatientPair's
    docstring."""
    result = await db.execute(
        select(DonorPatientPair).where(
            DonorPatientPair.id == pair_id,
            DonorPatientPair.doctor_id == doctor_id,
            DonorPatientPair.is_deleted.is_(False),
        )
    )
    pair = result.scalar_one_or_none()
    if pair is None:
        return None

    donor_result = await db.execute(select(Donor).where(Donor.id == pair.donor_id))
    donor = donor_result.scalar_one()
    assert_intended_recipient_consistent(pair, donor)
    return pair


async def list_pairs_for_doctor(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    donor_id: uuid.UUID | None = None,
) -> list[DonorPatientPair]:
    query = select(DonorPatientPair).where(
        DonorPatientPair.doctor_id == doctor_id, DonorPatientPair.is_deleted.is_(False)
    )
    if patient_id is not None:
        query = query.where(DonorPatientPair.patient_id == patient_id)
    if donor_id is not None:
        query = query.where(DonorPatientPair.donor_id == donor_id)
    query = query.order_by(DonorPatientPair.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_pair(
    db: AsyncSession, pair: DonorPatientPair, commit: bool = True
) -> DonorPatientPair:
    """Soft-delete, same pattern as delete_patient/delete_donor -- frees the
    (patient_id, donor_id) combination for re-registration (see the active
    partial-unique index on donor_patient_pairs)."""
    pair.is_deleted = True
    pair.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(pair)
    return pair


def assert_intended_recipient_consistent(pair: DonorPatientPair, donor: Donor) -> None:
    """Raises IntendedRecipientMismatch rather than silently reconciling --
    see DonorPatientPair's docstring for why this drift is possible and why
    detection happens here (every pair read) instead of at donor-write
    time."""
    if donor.intended_recipient_id != pair.patient_id:
        raise IntendedRecipientMismatch(pair.id, donor.id)

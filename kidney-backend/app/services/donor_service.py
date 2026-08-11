import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.enums import DonorStatus
from app.schemas.donor import DonorCreate, DonorUpdate
from app.services.hla_typing_service import _resolve_verified


async def create_donor(
    db: AsyncSession, doctor_id: uuid.UUID, payload: DonorCreate, commit: bool = True
) -> Donor:
    """commit=False lets a caller fold this write into the same transaction
    as a paired create_audit_log call (see create_audit_log's docstring) so
    a crash between the two can't leave one without the other."""
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
        sex=payload.sex,
        race=payload.race,
        smoking_status=payload.smoking_status,
        creatinine=payload.creatinine,
        urine_acr=payload.urine_acr,
        is_on_antihypertensive_medication=payload.is_on_antihypertensive_medication,
        family_history_kidney_disease=payload.family_history_kidney_disease,
        weight_kg=payload.weight_kg,
        is_biologically_related=payload.is_biologically_related,
        intended_recipient_id=payload.intended_recipient_id,
        details_verified=True if payload.details_verified is None else payload.details_verified,
    )
    db.add(donor)
    await db.flush()
    if commit:
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


async def delete_donor(db: AsyncSession, donor: Donor, commit: bool = True) -> Donor:
    """Soft-delete: hides the donor from lists/searches while keeping the
    row (and its HLA typings, report files, match reports) for audit
    history — hard-deleting would hit FK RESTRICT on any of those.
    commit=False — see create_donor's docstring."""
    donor.is_deleted = True
    donor.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(donor)
    return donor


class IllegalDonorStatusTransition(Exception):
    """Raised by update_donor_status when `status` isn't reachable from the
    donor's current status -- see _ALLOWED_TRANSITIONS."""

    def __init__(self, current: DonorStatus, requested: DonorStatus):
        self.current = current
        self.requested = requested
        super().__init__(
            f"Cannot transition donor status from {current.value!r} to {requested.value!r}"
        )


# Explicit transition matrix (added for the status-transition validation gap
# found in review #2: every status used to accept every other status
# unconditionally, so `transplanted -> available`, `deceased -> available`,
# and `medically_unfit -> available` all returned 200 and silently
# re-entered a transplanted/deceased/ruled-out donor into cross-hospital
# search and the exchange pool as a live organ).
# TRANSPLANTED and DECEASED are terminal -- nothing reachable from either.
# MEDICALLY_UNFIT and WITHDRAWN can still move forward (re-evaluation,
# eventual death) but never back into AVAILABLE/RESERVED/TRANSPLANTED --
# once ruled out or withdrawn, re-entering the pool needs a fresh
# determination, not a silent status flip.
_ALLOWED_TRANSITIONS: dict[DonorStatus, set[DonorStatus]] = {
    DonorStatus.AVAILABLE: {
        DonorStatus.RESERVED,
        DonorStatus.UNDER_WORKUP,
        DonorStatus.TRANSPLANTED,
        DonorStatus.MEDICALLY_UNFIT,
        DonorStatus.WITHDRAWN,
        DonorStatus.DECEASED,
    },
    DonorStatus.RESERVED: {
        DonorStatus.AVAILABLE,
        DonorStatus.UNDER_WORKUP,
        DonorStatus.TRANSPLANTED,
        DonorStatus.MEDICALLY_UNFIT,
        DonorStatus.WITHDRAWN,
        DonorStatus.DECEASED,
    },
    DonorStatus.UNDER_WORKUP: {
        DonorStatus.AVAILABLE,
        DonorStatus.RESERVED,
        DonorStatus.TRANSPLANTED,
        DonorStatus.MEDICALLY_UNFIT,
        DonorStatus.WITHDRAWN,
        DonorStatus.DECEASED,
    },
    DonorStatus.MEDICALLY_UNFIT: {
        DonorStatus.UNDER_WORKUP,
        DonorStatus.WITHDRAWN,
        DonorStatus.DECEASED,
    },
    DonorStatus.WITHDRAWN: {DonorStatus.DECEASED},
    DonorStatus.TRANSPLANTED: set(),
    DonorStatus.DECEASED: set(),
}


async def update_donor_status(
    db: AsyncSession, donor: Donor, status: DonorStatus, commit: bool = True
) -> Donor:
    """commit=False — see create_donor's docstring. Raises
    IllegalDonorStatusTransition (caught by the API layer as a 409) if
    `status` isn't reachable from the donor's current status."""
    if status != donor.status and status not in _ALLOWED_TRANSITIONS[donor.status]:
        raise IllegalDonorStatusTransition(donor.status, status)
    donor.status = status
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(donor)
    return donor


async def update_donor_details(
    db: AsyncSession, donor: Donor, payload: DonorUpdate, commit: bool = True
) -> Donor:
    """commit=False — see create_donor's docstring."""
    donor.full_name = payload.full_name
    donor.date_of_birth = payload.date_of_birth
    donor.nic_number = payload.nic_number
    donor.egfr = payload.egfr
    donor.systolic_bp = payload.systolic_bp
    donor.diastolic_bp = payload.diastolic_bp
    donor.bmi = payload.bmi
    donor.has_diabetes = payload.has_diabetes
    donor.sex = payload.sex
    donor.race = payload.race
    donor.smoking_status = payload.smoking_status
    donor.creatinine = payload.creatinine
    donor.urine_acr = payload.urine_acr
    donor.is_on_antihypertensive_medication = payload.is_on_antihypertensive_medication
    donor.family_history_kidney_disease = payload.family_history_kidney_disease
    donor.weight_kg = payload.weight_kg
    donor.is_biologically_related = payload.is_biologically_related
    donor.intended_recipient_id = payload.intended_recipient_id
    donor.details_verified = _resolve_verified(payload.details_verified, donor.details_verified)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(donor)
    return donor


async def get_donor_for_compatibility_check(
    db: AsyncSession, donor_id: uuid.UUID, doctor_id: uuid.UUID
) -> Donor | None:
    """Resolves a donor for POST /compatibility/check: the calling doctor's
    own donor (any status), OR a donor owned by a different doctor iff it's
    currently AVAILABLE and has no intended_recipient_id. Deliberately
    separate from get_donor_by_id_for_doctor (which stays owner-only for
    CRUD/HLA-typing endpoints) so opening up cross-hospital checks can't
    accidentally loosen anything else. Reads status fresh rather than
    trusting an earlier search result, so a donor reserved between search
    and submission cleanly 404s here.

    The intended_recipient_id check keeps this consistent with
    donor_search_service.py: a donor committed to a specific patient isn't
    available to any other doctor just because its ID leaked out some other
    way (e.g. it showed up in search before the recipient link was set).
    """
    result = await db.execute(
        select(Donor).where(Donor.id == donor_id, Donor.is_deleted.is_(False))
    )
    donor = result.scalar_one_or_none()
    if donor is None:
        return None
    if donor.doctor_id == doctor_id:
        return donor
    if donor.status == DonorStatus.AVAILABLE and donor.intended_recipient_id is None:
        return donor
    return None

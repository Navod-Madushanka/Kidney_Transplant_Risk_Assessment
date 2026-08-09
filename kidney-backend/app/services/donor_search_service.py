# app/services/donor_search_service.py
"""
Cross-hospital donor search: given a patient, prescreens every AVAILABLE
donor registered by any OTHER doctor for ABO compatibility and an A/B/DRB1
HLA mismatch estimate, returning a ranked candidate list. This is
deliberately cheap and read-only — no crossmatch, DSA, or cPRA — since those
either need a same-day lab result (crossmatch) or would be wasteful to run
against an entire pool up front. The full pipeline only runs once a doctor
picks one candidate and calls POST /compatibility/check.

Donors with an intended_recipient_id are excluded regardless of status:
most living donors in this system aren't free-floating organs, they're
someone's relative, donating only if that specific patient (who may belong
to a different doctor entirely) gets a kidney. Pooling them into every
other hospital's search treated living donation like deceased donation and
offered doctors a donor who was never actually available to them. Only
NULL (altruistic/deceased, or not yet linked to a recipient) is poolable.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor
from app.models.donor import Donor
from app.models.enums import DonorStatus
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.services.abo_service import ABOResult, check_abo_compatibility
from app.services.hla_mismatch_service import (
    MISMATCH_COUNTED_LOCI,
    MismatchResult,
    calculate_mismatch_result,
)
from app.services.hla_typing_service import (
    build_partial_typing_dict,
    get_donor_hla_typing_entries_bulk,
    get_patient_hla_typing_entries,
)


@dataclass
class DonorSearchCandidate:
    donor: Donor
    hospital_name: str
    doctor_full_name: str
    doctor_email: str
    abo_result: ABOResult
    mismatch_result: MismatchResult


async def search_compatible_donors(
    db: AsyncSession,
    patient: Patient,
    requesting_doctor_id: uuid.UUID,
) -> list[DonorSearchCandidate]:
    result = await db.execute(
        select(Donor, Doctor.full_name, Doctor.email, Hospital.name)
        .join(Doctor, Doctor.id == Donor.doctor_id)
        .join(Hospital, Hospital.id == Doctor.hospital_id)
        .where(
            Donor.status == DonorStatus.AVAILABLE,
            Donor.doctor_id != requesting_doctor_id,
            Donor.is_deleted.is_(False),
            Donor.intended_recipient_id.is_(None),
        )
    )
    rows = result.all()
    if not rows:
        return []

    patient_entries = await get_patient_hla_typing_entries(db, patient.id)
    patient_typing = build_partial_typing_dict(patient_entries, MISMATCH_COUNTED_LOCI)

    donor_ids = [donor.id for donor, _, _, _ in rows]
    donor_typing_entries = await get_donor_hla_typing_entries_bulk(db, donor_ids)

    candidates: list[DonorSearchCandidate] = []
    for donor, doctor_full_name, doctor_email, hospital_name in rows:
        abo_result = check_abo_compatibility(
            patient.blood_type.value, donor.blood_type.value
        )
        if not abo_result.is_compatible:
            continue

        donor_typing = build_partial_typing_dict(
            donor_typing_entries.get(donor.id, []), MISMATCH_COUNTED_LOCI
        )
        mismatch_result = calculate_mismatch_result(patient_typing, donor_typing)
        if mismatch_result.is_halted:
            continue

        candidates.append(
            DonorSearchCandidate(
                donor=donor,
                hospital_name=hospital_name,
                doctor_full_name=doctor_full_name,
                doctor_email=doctor_email,
                abo_result=abo_result,
                mismatch_result=mismatch_result,
            )
        )

    candidates.sort(key=lambda c: c.mismatch_result.total_mismatches)
    return candidates

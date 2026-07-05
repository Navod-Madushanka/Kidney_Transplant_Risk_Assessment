# app/services/hla_typing_service.py
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor_hla_typing import DonorHLATyping
from app.models.patient_hla_typing import PatientHLATyping
from app.reference_data.hla_loci import HLA_LOCI
from app.schemas.hla_typing import HLATypingEntry


async def get_patient_hla_typing_dict(
    db: AsyncSession, patient_id: uuid.UUID
) -> dict[str, list[str]]:
    result = await db.execute(
        select(PatientHLATyping).where(PatientHLATyping.patient_id == patient_id)
    )
    typing_rows = result.scalars().all()

    typing_dict = {
        row.locus.value: [row.allele_1, row.allele_2] for row in typing_rows
    }

    missing_loci = set(HLA_LOCI) - set(typing_dict.keys())
    if missing_loci:
        raise ValueError(
            f"Patient {patient_id} is missing HLA typing data for loci: {sorted(missing_loci)}"
        )

    return typing_dict


async def replace_patient_hla_typing(
    db: AsyncSession, patient_id: uuid.UUID, entries: list[HLATypingEntry]
) -> None:
    await db.execute(
        delete(PatientHLATyping).where(PatientHLATyping.patient_id == patient_id)
    )

    for entry in entries:
        typing_row = PatientHLATyping(
            patient_id=patient_id,
            locus=entry.locus,
            allele_1=entry.allele_1,
            allele_2=entry.allele_2,
        )
        db.add(typing_row)

    await db.commit()


async def get_donor_hla_typing_dict(
    db: AsyncSession, donor_id: uuid.UUID
) -> dict[str, list[str]]:
    result = await db.execute(
        select(DonorHLATyping).where(DonorHLATyping.donor_id == donor_id)
    )
    typing_rows = result.scalars().all()

    typing_dict = {
        row.locus.value: [row.allele_1, row.allele_2] for row in typing_rows
    }

    missing_loci = set(HLA_LOCI) - set(typing_dict.keys())
    if missing_loci:
        raise ValueError(
            f"Donor {donor_id} is missing HLA typing data for loci: {sorted(missing_loci)}"
        )

    return typing_dict


async def replace_donor_hla_typing(
    db: AsyncSession, donor_id: uuid.UUID, entries: list[HLATypingEntry]
) -> None:
    await db.execute(
        delete(DonorHLATyping).where(DonorHLATyping.donor_id == donor_id)
    )

    for entry in entries:
        typing_row = DonorHLATyping(
            donor_id=donor_id,
            locus=entry.locus,
            allele_1=entry.allele_1,
            allele_2=entry.allele_2,
        )
        db.add(typing_row)

    await db.commit()


async def get_population_hla_profiles(db: AsyncSession) -> list[list[str]]:
    patient_result = await db.execute(select(PatientHLATyping))
    patient_rows = patient_result.scalars().all()

    donor_result = await db.execute(select(DonorHLATyping))
    donor_rows = donor_result.scalars().all()

    profiles_by_person: dict[uuid.UUID, list[str]] = {}

    for row in patient_rows:
        profiles_by_person.setdefault(row.patient_id, []).extend(
            [row.allele_1, row.allele_2]
        )

    for row in donor_rows:
        profiles_by_person.setdefault(row.donor_id, []).extend(
            [row.allele_1, row.allele_2]
        )

    return list(profiles_by_person.values())
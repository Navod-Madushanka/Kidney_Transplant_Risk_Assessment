# app/services/hla_typing_service.py
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor_hla_typing import DonorHLATyping
from app.models.patient_hla_typing import PatientHLATyping
from app.reference_data.hla_loci import HLA_LOCI
from app.schemas.hla_typing import HLATypingEntry


def hla_antigen_designation(locus: str, allele: str) -> str:
    """Combines a locus and a raw allele string into the antigen
    "designation" used everywhere antibody antigens are named (e.g. locus
    "B" + allele "07" -> "B7"). HLA typing rows store the locus and allele
    separately with zero-padded allele numbers (see COMPATIBLE_DONOR_HLA in
    app/tests/conftest.py), while antibody-profile antigens are recorded
    against the combined, non-padded designation (see
    app/schemas/antibody_profile.py / the DSA test data). This is the single
    place that bridges the two so callers doing antigen-based matching (DSA
    checks, cPRA) don't each reimplement it slightly differently.
    """
    return f"{locus}{allele.lstrip('0') or '0'}"


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


async def get_patient_hla_typings(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[HLATypingEntry]:
    """Returns the patient's HLA typing rows shaped for the API response
    (list[HLATypingEntry]), unlike get_patient_hla_typing_dict which returns
    a locus->alleles dict for the scoring pipeline and requires every locus
    to be present. This one is fine returning a partial or empty list, since
    it's for the GET endpoint the frontend uses to populate the editor.
    """
    entries = await get_patient_hla_typing_entries(db, patient_id)
    return [
        HLATypingEntry(locus=row.locus, allele_1=row.allele_1, allele_2=row.allele_2)
        for row in entries
    ]


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


async def get_donor_hla_typings(
    db: AsyncSession, donor_id: uuid.UUID
) -> list[HLATypingEntry]:
    """Same rationale as get_patient_hla_typings above — shaped for the
    donor HLA-typing GET endpoint, no completeness requirement.
    """
    entries = await get_donor_hla_typing_entries(db, donor_id)
    return [
        HLATypingEntry(locus=row.locus, allele_1=row.allele_1, allele_2=row.allele_2)
        for row in entries
    ]


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


async def get_patient_hla_typing_entries(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[PatientHLATyping]:
    result = await db.execute(
        select(PatientHLATyping).where(PatientHLATyping.patient_id == patient_id)
    )
    return list(result.scalars().all())


async def get_donor_hla_typing_entries(
    db: AsyncSession, donor_id: uuid.UUID
) -> list[DonorHLATyping]:
    result = await db.execute(
        select(DonorHLATyping).where(DonorHLATyping.donor_id == donor_id)
    )
    return list(result.scalars().all())


def build_partial_typing_dict(entries: list, loci: tuple[str, ...]) -> dict[str, list[str]]:
    """Builds a locus -> [allele_1, allele_2] dict restricted to `loci`,
    from either PatientHLATyping or DonorHLATyping rows — permissive like
    get_*_hla_typing_entries (an entirely missing locus just gets an empty
    list), unlike get_patient_hla_typing_dict / get_donor_hla_typing_dict
    which require a complete 9-locus panel and raise otherwise.

    Used by Step 3 of the sequential pipeline (hla_mismatch_service.py),
    which only ever needs A/B/DRB1 and must not block on the other 6 loci
    being filled in yet.
    """
    typing_dict: dict[str, list[str]] = {locus: [] for locus in loci}
    for row in entries:
        if row.locus.value in typing_dict:
            typing_dict[row.locus.value] = [row.allele_1, row.allele_2]
    return typing_dict

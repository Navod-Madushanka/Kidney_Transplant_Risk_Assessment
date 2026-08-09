# app/services/hla_typing_service.py
import re
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.donor_hla_typing import DonorHLATyping
from app.models.patient import Patient
from app.models.patient_hla_typing import PatientHLATyping
from app.reference_data.hla_loci import HLA_LOCI
from app.schemas.hla_typing import HLATypingEntry
from app.services.audit_service import create_audit_log


def _resolve_verified(ocr_verified: bool | None, previous_verified: bool) -> bool:
    """None means "no claim being made about this specific write" -> keep
    whatever the record's verified flag already was (`previous_verified`)
    rather than resetting it to trusted. For a brand-new patient/donor
    that's always True (the column's creation-time default), so a first-
    ever write with ocr_verified=None still resolves to trusted, same as
    manual entry always was. What changed (review #2 bug 5): a *replace*
    call with ocr_verified=None used to unconditionally reset to True even
    when the record's current value was False (unconfirmed OCR data) --
    e.g. PUT .../hla-typings with the query param simply omitted silently
    cleared an unverified flag with no trace, since omitting it is
    indistinguishable from a caller who deliberately means "trusted." An
    explicit True/False is only ever passed by the compatibility-check
    wizard, which knows whether this particular write came from an OCR
    extraction the doctor has (True) or hasn't (False) confirmed against
    the source document -- that always wins outright.
    """
    return previous_verified if ocr_verified is None else ocr_verified



# Real-world antibody screens (bead-specificity charts, and any doctor
# entering an antibody-profile row by hand) name DR/DQ/DP-locus antigens
# using the classic serological group prefix, not the molecular typing
# locus name -- "DR13", "DQ5", "DP4", never "DRB113"/"DQB105"/"DPB104". HLA-C
# is the same story for a different historical reason: its serological
# antigens are conventionally written "Cw1".."Cw18" (the "w" originally
# distinguished them from complement component names), never a bare "C1"
# etc. -- confirmed 2026-08-03 against a real bead-specificity chart, whose
# C-locus rows were 100% "CwN", zero bare "CN". Only A and B's molecular
# locus name genuinely matches their serological name unchanged. DQA1/DPA1
# (and the composite DRB3,4,5 locus, allele values like "DRB3*02") aren't
# part of this simple numeric scheme and are deliberately left unmapped
# rather than guessed at.
_SEROLOGICAL_LOCUS_PREFIX = {
    "DRB1": "DR",
    "DQB1": "DQ",
    "DPB1": "DP",
    "C": "Cw",
}

# Real bead-specificity charts often record a B-locus antigen combined with
# its broad Bw4/Bw6 cross-reactive-group split in one string -- "B45,Bw6",
# occasionally "B41.Bw6" (OCR reads a period instead of a comma) -- while
# hla_antigen_designation() above only ever builds the bare specific antigen
# ("B45"). The Bw4/Bw6 group is a separate serological classification, not
# part of the antigen's identity, so it must be stripped before comparing
# against a donor's designation or a real anti-B DSA is structurally
# unmatchable. Confirmed 2026-08-03: every single B-locus row extracted from
# a real chart carried this suffix (or was allele-level, out of scope -- see
# below) -- none were bare "B<number>".
#
# Deliberately narrow: only strips a trailing ",Bw<digits>" / ".Bw<digits>",
# so it never touches an allele-level designation ("B*07:02" -- a different,
# unmapped naming scheme entirely, see the module docstring) or an unrelated
# numeric suffix such as the OCR-mislabeling artifact "B40.01" seen on that
# same real chart (a separate, already-known extraction-accuracy bug, not
# this one -- fixing this pattern must not accidentally paper over that one).
_BW_SUFFIX_RE = re.compile(r"^(.*?)[,.]Bw\d+$", re.IGNORECASE)


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

    Real bug found 2026-08-02: A/B's molecular locus name already matches
    their serological name, so this worked for them, but DRB1/DQB1/DPB1
    don't -- a patient's real anti-DR13 antibody was silently invisible to
    the DSA check because it built "DRB113" and never matched "DR13". See
    _SEROLOGICAL_LOCUS_PREFIX above.

    Second real bug found 2026-08-03, same class: HLA-C isn't like A/B
    either -- its serological antigens need the "Cw" prefix, not the bare
    locus letter. See _SEROLOGICAL_LOCUS_PREFIX above, and
    normalize_antibody_antigen() below for the separate B-locus Bw4/Bw6
    suffix problem this doesn't cover.
    """
    prefix = _SEROLOGICAL_LOCUS_PREFIX.get(locus, locus)
    return f"{prefix}{allele.lstrip('0') or '0'}"


def normalize_antibody_antigen(antigen: str) -> str:
    """Strips a real chart's ",Bw4"/",Bw6" (or ".Bw4"/".Bw6") cross-reactive-
    group suffix from a B-locus antibody antigen string, e.g. "B45,Bw6" ->
    "B45", so it can exact-match a donor's bare hla_antigen_designation()
    output. Antigens without that suffix pass through unchanged. See the
    module-level comment on _BW_SUFFIX_RE for what this deliberately does
    NOT touch.
    """
    match = _BW_SUFFIX_RE.match(antigen.strip())
    return match.group(1) if match else antigen


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
    db: AsyncSession,
    patient_id: uuid.UUID,
    entries: list[HLATypingEntry],
    ocr_verified: bool | None = None,
    doctor_id: uuid.UUID | None = None,
) -> None:
    """doctor_id is only used to attribute the audit entry below -- omitted
    by internal/test callers that don't have a doctor in scope, in which
    case the write still happens but isn't audited (matches how every
    other write in this codebase requires a doctor to audit an action)."""
    previous_verified = (
        await db.execute(select(Patient.hla_typing_verified).where(Patient.id == patient_id))
    ).scalar_one()
    new_verified = _resolve_verified(ocr_verified, previous_verified)

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

    await db.execute(
        update(Patient).where(Patient.id == patient_id).values(hla_typing_verified=new_verified)
    )

    if doctor_id is not None:
        await create_audit_log(
            db,
            doctor_id=doctor_id,
            action="replaced_patient_hla_typing",
            patient_id=patient_id,
            details={
                "entry_count": len(entries),
                "previous_verified": previous_verified,
                "new_verified": new_verified,
            },
            commit=False,
        )
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
    db: AsyncSession,
    donor_id: uuid.UUID,
    entries: list[HLATypingEntry],
    ocr_verified: bool | None = None,
    doctor_id: uuid.UUID | None = None,
) -> None:
    """doctor_id — see replace_patient_hla_typing's docstring, same contract."""
    previous_verified = (
        await db.execute(select(Donor.hla_typing_verified).where(Donor.id == donor_id))
    ).scalar_one()
    new_verified = _resolve_verified(ocr_verified, previous_verified)

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

    await db.execute(
        update(Donor).where(Donor.id == donor_id).values(hla_typing_verified=new_verified)
    )

    if doctor_id is not None:
        await create_audit_log(
            db,
            doctor_id=doctor_id,
            action="replaced_donor_hla_typing",
            donor_id=donor_id,
            details={
                "entry_count": len(entries),
                "previous_verified": previous_verified,
                "new_verified": new_verified,
            },
            commit=False,
        )
    await db.commit()


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


async def get_donor_hla_typing_entries_bulk(
    db: AsyncSession, donor_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[DonorHLATyping]]:
    """Same rows as get_donor_hla_typing_entries but for many donors in one
    query, grouped by donor_id — used by donor_search_service to avoid
    firing one query per candidate donor in the pool.
    """
    if not donor_ids:
        return {}

    result = await db.execute(
        select(DonorHLATyping).where(DonorHLATyping.donor_id.in_(donor_ids))
    )
    entries_by_donor: dict[uuid.UUID, list[DonorHLATyping]] = {}
    for row in result.scalars().all():
        entries_by_donor.setdefault(row.donor_id, []).append(row)
    return entries_by_donor


async def get_patient_hla_typing_entries_bulk(
    db: AsyncSession, patient_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PatientHLATyping]]:
    """Same rows as get_patient_hla_typing_entries but for many patients in
    one query, grouped by patient_id — mirrors get_donor_hla_typing_entries_
    bulk above. Used by exchange_graph_service, which scores every donor in
    an exchange pool against every OTHER pool member's recipient and would
    otherwise fire one query per patient.
    """
    if not patient_ids:
        return {}

    result = await db.execute(
        select(PatientHLATyping).where(PatientHLATyping.patient_id.in_(patient_ids))
    )
    entries_by_patient: dict[uuid.UUID, list[PatientHLATyping]] = {}
    for row in result.scalars().all():
        entries_by_patient.setdefault(row.patient_id, []).append(row)
    return entries_by_patient


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

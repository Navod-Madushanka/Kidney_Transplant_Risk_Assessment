# app/services/sensitization_event_service.py
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sensitization_event import SensitizationEvent
from app.schemas.sensitization_event import SensitizationEventEntry
from app.services.audit_service import create_audit_log


async def create_sensitization_events(
    db: AsyncSession, patient_id: uuid.UUID, entries: list[SensitizationEventEntry]
) -> list[SensitizationEvent]:
    new_events = []

    for entry in entries:
        event = SensitizationEvent(
            patient_id=patient_id,
            event_type=entry.event_type,
            event_date=entry.event_date,
        )
        db.add(event)
        new_events.append(event)

    await db.commit()

    for event in new_events:
        await db.refresh(event)

    return new_events


async def replace_sensitization_events(
    db: AsyncSession,
    patient_id: uuid.UUID,
    entries: list[SensitizationEventEntry],
    doctor_id: uuid.UUID | None = None,
) -> list[SensitizationEvent]:
    """Delete-then-insert, mirroring hla_typing_service.replace_patient_hla_
    typing / antibody_profile_service.replace_patient_antibody_profiles --
    the same replace-not-append shape. Exists because create_sensitization_
    events (POST, above) is additive: the compatibility-check wizard's
    sensitization step is three booleans, an inherently complete statement
    of the current set, and calling POST against a *linked* (not
    freshly-created) patient on every re-run of a check would re-add the
    same events and double, then triple, calculate_sensitization_score's
    total. POST is kept unchanged for the patient detail page's "add one
    event" flow, which is genuinely additive."""
    previous_count = (
        await db.execute(
            select(SensitizationEvent).where(SensitizationEvent.patient_id == patient_id)
        )
    ).scalars().all()
    previous_count = len(previous_count)

    await db.execute(
        delete(SensitizationEvent).where(SensitizationEvent.patient_id == patient_id)
    )

    new_events = []
    for entry in entries:
        event = SensitizationEvent(
            patient_id=patient_id,
            event_type=entry.event_type,
            event_date=entry.event_date,
        )
        db.add(event)
        new_events.append(event)

    if doctor_id is not None:
        await create_audit_log(
            db,
            doctor_id=doctor_id,
            action="replaced_patient_sensitization_events",
            patient_id=patient_id,
            details={"previous_count": previous_count, "new_count": len(new_events)},
            commit=False,
        )

    await db.commit()
    for event in new_events:
        await db.refresh(event)

    return new_events


async def get_patient_sensitization_event_types(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[str]:
    result = await db.execute(
        select(SensitizationEvent).where(SensitizationEvent.patient_id == patient_id)
    )
    events = result.scalars().all()

    return [event.event_type.value for event in events]


async def get_sensitization_events_for_patient(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[SensitizationEvent]:
    """Returns the full ORM rows (not just event_type strings), for the
    GET .../sensitization-events endpoint which serializes via
    SensitizationEventResponse.model_validate — that needs id, event_date,
    created_at, etc., not just the event_type used by the scoring pipeline.
    """
    result = await db.execute(
        select(SensitizationEvent)
        .where(SensitizationEvent.patient_id == patient_id)
        .order_by(SensitizationEvent.event_date.desc())
    )
    return list(result.scalars().all())

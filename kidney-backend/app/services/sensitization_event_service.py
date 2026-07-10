# app/services/sensitization_event_service.py
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sensitization_event import SensitizationEvent
from app.schemas.sensitization_event import SensitizationEventEntry


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
    """Get all sensitization events for a patient."""
    result = await db.execute(
        select(SensitizationEvent)
        .where(SensitizationEvent.patient_id == patient_id)
        .order_by(SensitizationEvent.event_date.desc())  # most recent first
    )
    return list(result.scalars().all())
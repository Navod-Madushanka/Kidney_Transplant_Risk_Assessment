# app/models/sensitization_event.py
import uuid
from datetime import date

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import SensitizationEventTypeEnum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SensitizationEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sensitization_events"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"), nullable=False, index=True
    )
    event_type: Mapped[SensitizationEventTypeEnum] = mapped_column(
        Enum(SensitizationEventTypeEnum, name="sensitization_event_type_enum", create_type=False),
        nullable=False,
    )
    event_date: Mapped[date] = mapped_column(nullable=False)
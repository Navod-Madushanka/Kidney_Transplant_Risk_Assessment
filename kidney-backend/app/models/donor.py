# app/models/donor.py
import uuid
from datetime import date

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import BloodType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Donor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "donors"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(nullable=False)
    date_of_birth: Mapped[date] = mapped_column(nullable=False)
    blood_type: Mapped[BloodType] = mapped_column(
    Enum(
        BloodType,
        name="blood_type_enum",
        values_callable=lambda enum_class: [member.value for member in enum_class],
    ),
    nullable=False,
    )
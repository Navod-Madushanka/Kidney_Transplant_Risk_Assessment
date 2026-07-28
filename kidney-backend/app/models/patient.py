# app/models/patient.py
import uuid
from datetime import date

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import BloodType, RhFactor
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Patient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "patients"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(nullable=False)
    date_of_birth: Mapped[date] = mapped_column(nullable=False)
    nic_number: Mapped[str | None] = mapped_column(unique=True, nullable=True, index=True)
    blood_type: Mapped[BloodType] = mapped_column(
        Enum(
            BloodType,
            name="blood_type_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    rh_factor: Mapped[RhFactor] = mapped_column(
        Enum(
            RhFactor,
            name="rh_factor_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )

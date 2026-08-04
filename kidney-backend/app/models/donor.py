# app/models/donor.py
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import BloodType, DonorStatus, RhFactor
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Donor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "donors"
    # Plain unique=True would keep a soft-deleted donor's NIC permanently
    # reserved (see is_deleted below), blocking re-registration of a real
    # person after their old record was deleted. Scoping the uniqueness to
    # active rows only lets a NIC be reused once its prior record is gone.
    __table_args__ = (
        Index(
            "ix_donors_nic_number_active_unique",
            "nic_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(nullable=False)
    date_of_birth: Mapped[date] = mapped_column(nullable=False)
    nic_number: Mapped[str | None] = mapped_column(nullable=True, index=True)
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
    status: Mapped[DonorStatus] = mapped_column(
        Enum(
            DonorStatus,
            name="donor_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
        default=DonorStatus.AVAILABLE,
        server_default=DonorStatus.AVAILABLE.value,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

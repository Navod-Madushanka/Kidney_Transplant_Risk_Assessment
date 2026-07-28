# app/models/doctor.py
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Doctor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "doctors"

    hospital_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospitals.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(nullable=False)
    full_name: Mapped[str] = mapped_column(nullable=False)

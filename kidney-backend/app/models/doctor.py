# app/models/doctor.py
import uuid

from sqlalchemy import Boolean, ForeignKey
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

    # Added 2026-08-09 (review #2 bug 12): system-wide operations like
    # /audit-logs/verify were gated on "any authenticated doctor" only --
    # there was no role/permission concept anywhere in this data model to
    # gate them more tightly with. No self-service promotion path exists
    # (or should exist without a lot more design work than this one bug
    # warrants) -- an operator sets this directly in the database. See
    # docs/clinical-basis.md's sibling doc-comment style: this is a
    # deliberately minimal, single-flag start, not a full role system.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

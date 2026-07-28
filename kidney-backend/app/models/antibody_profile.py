# app/models/antibody_profile.py
import uuid

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AntibodyProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "antibody_profiles"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"), nullable=False, index=True
    )
    antigen: Mapped[str] = mapped_column(nullable=False)
    mfi: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

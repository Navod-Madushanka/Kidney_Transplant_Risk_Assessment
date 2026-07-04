# app/models/patient_hla_typing.py
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import HLALocusEnum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PatientHLATyping(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "patient_hla_typings"
    __table_args__ = (UniqueConstraint("patient_id", "locus"),)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"), nullable=False, index=True
    )
    locus: Mapped[HLALocusEnum] = mapped_column(
        Enum(HLALocusEnum, name="hla_locus_enum", create_type=False), nullable=False
    )
    allele_1: Mapped[str] = mapped_column(nullable=False)
    allele_2: Mapped[str] = mapped_column(nullable=False)
# app/models/donor_hla_typing.py
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import HLALocusEnum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DonorHLATyping(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "donor_hla_typings"
    __table_args__ = (UniqueConstraint("donor_id", "locus"),)

    donor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donors.id"), nullable=False, index=True
    )
    locus: Mapped[HLALocusEnum] = mapped_column(
    Enum(
        HLALocusEnum,
        name="hla_locus_enum",
        create_type=False,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    ),
    nullable=False,
    )
    allele_1: Mapped[str] = mapped_column(nullable=False)
    allele_2: Mapped[str] = mapped_column(nullable=False)

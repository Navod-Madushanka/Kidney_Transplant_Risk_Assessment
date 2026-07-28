# app/models/match_report.py
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MatchReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "match_reports"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"), nullable=False, index=True
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donors.id"), nullable=False, index=True
    )

    overall_status: Mapped[str] = mapped_column(String(50), nullable=False)

    abo_result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dsa_result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    sensitization_result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    hla_scoring_result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    cpra_result: Mapped[dict] = mapped_column(JSONB, nullable=True)

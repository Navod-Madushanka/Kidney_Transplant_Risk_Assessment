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

    # Added for the Step 1-7 sequential pipeline (see the roadmap's Phase 3,
    # "Clinical Pipeline Redesign"). mismatch_result/pra_bucket_result are
    # Steps 3 and 4; crossmatch_result is Step 6; final_risk_level is the
    # Step 7 classification (Low Risk / Low-Average Risk / High-Average
    # Risk / High Risk) — kept as its own string column, unlike the legacy
    # risk_tier, which was never persisted and is only re-derived on the
    # frontend from hla_scoring_result.
    mismatch_result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    pra_bucket_result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    crossmatch_result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    final_risk_level: Mapped[str] = mapped_column(String(50), nullable=True)

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

    # The single headline verdict for this report (see
    # app/reference_data/report_outcome.py) — computed once by
    # run_match_pipeline and stored alongside the raw step results rather
    # than re-derived on every read, so a later change to the decision
    # table doesn't silently reinterpret an old report. nullable=True
    # because this was added after reports already existed; see the
    # migration that backfills it for pre-existing rows.
    outcome: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # LKDPI score (see app/reference_data/lkdpi_model.py, app/services/
    # lkdpi_service.py) -- computed after Step 7, only when the verdict
    # isn't not_compatible (see match_pipeline.py). Null both for halted
    # reports (nothing to score) and for pre-existing reports created
    # before this column existed.
    lkdpi_result: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # A snapshot of app/reference_data/versions.CLINICAL_REFERENCE_VERSIONS
    # at the moment this report was created -- so a later doctor-approved
    # change to, say, the DSA bands or risk tiers doesn't silently
    # reinterpret what an old report's numbers meant (see that module's
    # docstring). nullable=True because this was added after reports
    # already existed; pre-existing rows are simply left null rather than
    # backfilled with a guess at what version was in force when they were
    # generated.
    reference_versions: Mapped[dict] = mapped_column(JSONB, nullable=True)

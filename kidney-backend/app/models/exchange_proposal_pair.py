# app/models/exchange_proposal_pair.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ExchangeProposalPairDecision
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ExchangeProposalPair(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One pair in a proposed exchange cycle (Part K, K2/K3).

    `is_open` is True exactly while the parent ExchangeProposal is
    `proposed` or `accepted`, False once the proposal reaches any terminal
    status. It backs the partial unique index below -- the actual overlap
    invariant ("a donor may be in at most one open proposal") lives in
    Postgres, not application code alone: two simultaneous proposals over
    the same donor race to insert this row, and the database itself is the
    thing that guarantees only one wins.

    Written ONLY by exchange_proposal_service.transition_proposal_status,
    in the same transaction as the parent's `status` column -- see that
    function's docstring. Every other caller goes through it.
    """

    __tablename__ = "exchange_proposal_pairs"
    __table_args__ = (
        Index(
            "ix_exchange_proposal_pairs_donor_id_open_unique",
            "donor_id",
            unique=True,
            postgresql_where=text("is_open"),
        ),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exchange_proposals.id"), nullable=False, index=True
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donors.id"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"), nullable=False, index=True
    )
    # Denormalised from Donor.doctor_id at creation (K2) so "proposals
    # awaiting my decision" is one indexed query, not a join through donors
    # on every poll. The donor's doctor decides, not the recipient's -- see
    # K5's "which doctor owns a pair" note: it's the donor's organ being
    # committed, and the donor status transition (AVAILABLE -> RESERVED) is
    # the one that doctor is already authorised for.
    owning_doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id"), nullable=False, index=True
    )
    decision: Mapped[ExchangeProposalPairDecision] = mapped_column(
        Enum(
            ExchangeProposalPairDecision,
            name="exchange_proposal_pair_decision_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
        default=ExchangeProposalPairDecision.PENDING,
        server_default=ExchangeProposalPairDecision.PENDING.value,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("doctors.id"), nullable=True
    )
    decline_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

# app/models/exchange_proposal.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ExchangeProposalStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ExchangeProposal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A discovered exchange cycle a doctor has proposed for commitment
    (Part K, K2). Mirrors MatchReport's snapshot convention: `cycle_snapshot`
    freezes the clinical picture -- nodes, directed edges, every
    mismatch_result/dsa_result/lkdpi_result, plus HLA_FREQUENCY_TABLE_VERSION
    and the DSA band constants in force -- AS COMPUTED AT PROPOSAL TIME, the
    same way MatchReport bakes reference-data versions into its own JSONB
    columns rather than a separate version table. A proposal accepted on
    Thursday must show the clinical picture it was accepted on, not a
    re-run against a pool that has since changed.

    `status` transitions ONLY through exchange_proposal_service.
    transition_proposal_status -- see that module's docstring for why
    that's a hard rule, not a convention: it's the one place that keeps
    this row's status and every child ExchangeProposalPair.is_open
    (K3's overlap invariant) in the same transaction.
    """

    __tablename__ = "exchange_proposals"

    created_by_doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id"), nullable=False, index=True
    )
    # The WEIGHT_POLICIES key in force when this cycle was proposed -- see
    # exchange_matching_service.WEIGHT_POLICIES.
    policy: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[ExchangeProposalStatus] = mapped_column(
        Enum(
            ExchangeProposalStatus,
            name="exchange_proposal_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
        default=ExchangeProposalStatus.PROPOSED,
        server_default=ExchangeProposalStatus.PROPOSED.value,
    )
    cycle_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

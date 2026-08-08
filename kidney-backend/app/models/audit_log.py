# app/models/audit_log.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    doctor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(nullable=True, index=True)
    donor_id: Mapped[uuid.UUID] = mapped_column(nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # server_default is a defensive fallback only — app/services/audit_service.py
    # always sets this explicitly on the object before flush, since the hash
    # chain below needs the exact timestamp value at hashing time, before the
    # row is ever sent to the database.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Hash chain (added 2026-08-08 — see audit_service.compute_audit_hash):
    # prev_hash is the previous row's `hash` (or GENESIS_HASH for the first
    # row ever written); hash is sha256 over
    # (prev_hash, doctor_id, patient_id, donor_id, action, created_at, details).
    # A retroactive UPDATE or DELETE on any row breaks this chain for every
    # row after it — verify_audit_chain() walks the table and recomputes it
    # to detect that. Ordinary Postgres UPDATE/DELETE privileges on this
    # table make the chain tamper-evident, not tamper-proof; see that
    # function's docstring for what "tamper-evident" does and doesn't cover
    # here.
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

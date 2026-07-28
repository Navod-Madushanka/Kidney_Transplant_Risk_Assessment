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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

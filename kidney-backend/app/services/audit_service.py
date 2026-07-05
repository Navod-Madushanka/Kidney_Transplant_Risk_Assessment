# app/services/audit_service.py
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def create_audit_log(
    db: AsyncSession,
    doctor_id: uuid.UUID,
    action: str,
    patient_id: Optional[uuid.UUID] = None,
    donor_id: Optional[uuid.UUID] = None,
    details: Optional[dict] = None,
) -> AuditLog:
    log_entry = AuditLog(
        doctor_id=doctor_id,
        action=action,
        patient_id=patient_id,
        donor_id=donor_id,
        details=details,
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

    return log_entry
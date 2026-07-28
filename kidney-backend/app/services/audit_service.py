# app/services/audit_service.py
import uuid
from typing import Optional

from sqlalchemy import func, select
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


async def get_audit_logs(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
) -> tuple[list[AuditLog], int]:
    """Returns (rows, total_count) for the given page/filters, newest first.

    total_count is the count across ALL matching rows (ignoring limit/offset),
    so the frontend can render "Page 2 of 14" style pagination.
    """
    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if doctor_id is not None:
        query = query.where(AuditLog.doctor_id == doctor_id)
        count_query = count_query.where(AuditLog.doctor_id == doctor_id)

    if patient_id is not None:
        query = query.where(AuditLog.patient_id == patient_id)
        count_query = count_query.where(AuditLog.patient_id == patient_id)

    if action is not None:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    rows = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total_count = total_result.scalar_one()

    return rows, total_count

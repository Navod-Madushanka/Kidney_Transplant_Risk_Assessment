# app/api/audit_logs.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.audit_log import AuditChainVerificationResponse, AuditLogListResponse
from app.services.audit_service import get_audit_logs, verify_audit_chain

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("/verify", response_model=AuditChainVerificationResponse)
async def verify_audit_chain_endpoint(
    current_doctor: Doctor = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Recomputes the audit_logs hash chain end to end and reports whether
    it's intact -- see audit_service.verify_audit_chain's docstring for
    exactly what this does and doesn't prove. Not scoped to the requesting
    doctor: chain integrity is a system-wide property, not per-doctor data.
    Admin-only (review #2 bug 12) -- this exposes every doctor's activity
    across the whole system, not just the caller's own.
    """
    return await verify_audit_chain(db)


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_doctor: Doctor = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only, system-wide audit log listing, newest first. Previously
    dead code (get_audit_logs existed with no route calling it -- review
    #2 bug 24); wired up here now that there's an admin gate worth putting
    it behind.
    """
    rows, total_count = await get_audit_logs(db, limit=limit, offset=offset)
    return AuditLogListResponse(rows=rows, total_count=total_count)

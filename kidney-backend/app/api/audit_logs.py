# app/api/audit_logs.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.audit_log import AuditChainVerificationResponse
from app.services.audit_service import verify_audit_chain

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("/verify", response_model=AuditChainVerificationResponse)
async def verify_audit_chain_endpoint(
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recomputes the audit_logs hash chain end to end and reports whether
    it's intact -- see audit_service.verify_audit_chain's docstring for
    exactly what this does and doesn't prove. Not scoped to the requesting
    doctor: chain integrity is a system-wide property, not per-doctor data.
    """
    return await verify_audit_chain(db)

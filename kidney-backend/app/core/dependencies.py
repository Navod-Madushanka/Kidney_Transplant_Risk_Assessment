# app/core/dependencies.py
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.doctor import Doctor
from app.services.doctor_service import get_doctor_by_id

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Doctor:
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        doctor_id_str = payload.get("sub")
        if doctor_id_str is None:
            raise credentials_exception
        doctor_id = uuid.UUID(doctor_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    doctor = await get_doctor_by_id(db, doctor_id)
    if doctor is None:
        raise credentials_exception

    return doctor


async def require_admin(current_doctor: Doctor = Depends(get_current_user)) -> Doctor:
    """Gate for system-wide operations (e.g. /audit-logs) that shouldn't be
    reachable by every authenticated doctor -- see Doctor.is_admin's
    docstring. Re-checks the doctor row's current is_admin value on every
    request (get_current_user always re-fetches from the DB, never trusts
    the JWT payload alone), so revoking admin access takes effect
    immediately rather than waiting for existing tokens to expire.
    """
    if not current_doctor.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an administrator account.",
        )
    return current_doctor

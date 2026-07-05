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
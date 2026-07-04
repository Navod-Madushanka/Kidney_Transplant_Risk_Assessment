# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.doctor_service import get_doctor_by_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    doctor = await get_doctor_by_email(db, credentials.email)

    if doctor is None or not verify_password(credentials.password, doctor.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(
        data={
            "sub": str(doctor.id),
            "hospital_id": str(doctor.hospital_id),
            "role": "doctor",
        }
    )

    return TokenResponse(access_token=access_token)
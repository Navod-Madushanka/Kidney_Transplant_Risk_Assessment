# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.doctor_service import create_doctor, get_doctor_by_email
from app.services.hospital_service import get_or_create_hospital

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing_doctor = await get_doctor_by_email(db, payload.email)
    if existing_doctor is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists",
        )

    hospital = await get_or_create_hospital(db, payload.hospital_name)

    doctor = await create_doctor(
        db,
        hospital_id=hospital.id,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )

    await db.commit()

    access_token = create_access_token(
        data={
            "sub": str(doctor.id),
            "hospital_id": str(doctor.hospital_id),
            "role": "doctor",
        }
    )

    return TokenResponse(access_token=access_token)


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

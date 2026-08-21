# app/api/auth.py
#
# There is no POST /register here on purpose. Self-service signup would let
# anyone with network access to this API create a doctor account -- closed
# 2026-08-21 as part of making the system safe to expose. Accounts are
# created by an operator directly (see app/scripts/promote_admin.py's
# docstring for the full onboarding note); this router only authenticates
# accounts that already exist.
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
            # Real authorization always re-checks doctor.is_admin fresh
            # from the DB on every request (see require_admin in
            # app/core/dependencies.py) -- this claim is for the frontend
            # to decide what to show, not something any endpoint trusts
            # for access control, so a stale token can't grant stale admin
            # access.
            "role": "admin" if doctor.is_admin else "doctor",
        }
    )

    return TokenResponse(access_token=access_token)

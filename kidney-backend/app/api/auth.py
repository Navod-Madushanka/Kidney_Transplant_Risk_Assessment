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

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.doctor_service import get_doctor_by_email
from app.services.hospital_service import get_hospital_by_id

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


@router.get("/me", response_model=CurrentUserResponse)
async def read_current_user(
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # The frontend calls this right after login (and on session restore) to
    # get the doctor's name and hospital for the sidebar -- the JWT itself
    # only carries hospital_id/role, not anything display-worthy (see
    # login()'s access_token claims above).
    hospital = await get_hospital_by_id(db, current_doctor.hospital_id)

    return CurrentUserResponse(
        id=current_doctor.id,
        email=current_doctor.email,
        full_name=current_doctor.full_name,
        hospital_id=current_doctor.hospital_id,
        hospital_name=hospital.name if hospital else "",
        is_admin=current_doctor.is_admin,
    )

# app/api/auth.py
#
# There is no POST /register here on purpose. Self-service signup would let
# anyone with network access to this API create a doctor account -- closed
# 2026-08-21 as part of making the system safe to expose. Accounts are
# created by an operator directly (see app/scripts/promote_admin.py's
# docstring for the full onboarding note); this router only authenticates
# accounts that already exist.
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.logging import get_logger
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.doctor_service import get_doctor_by_email
from app.services.hospital_service import get_hospital_by_id
from app.services.login_throttle_service import account_throttle, get_client_ip, ip_throttle

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Normalized so "Doctor@Example.com" and "doctor@example.com" share one
    # counter -- get_doctor_by_email itself is presumably already
    # case-insensitive at the DB layer for the same reason; this just keeps
    # the throttle key consistent with that.
    email_key = credentials.email.strip().lower()
    ip_key = get_client_ip(request)

    # Checked before touching the DB or bcrypt at all -- the entire point
    # of throttling is to stop a locked-out attempt from costing anything,
    # not just to refuse it after the fact.
    wait_seconds = max(
        account_throttle.seconds_until_unlocked(email_key),
        ip_throttle.seconds_until_unlocked(ip_key),
    )
    if wait_seconds > 0:
        logger.warning(
            "login_throttled",
            extra={"email": email_key, "ip": ip_key, "retry_after_seconds": round(wait_seconds)},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(int(wait_seconds) + 1)},
        )

    doctor = await get_doctor_by_email(db, credentials.email)

    if doctor is None or not verify_password(credentials.password, doctor.hashed_password):
        # Recorded identically whether the email exists or not -- if the
        # response (or the time to produce it) ever differed based on that,
        # the throttle itself would become a way to enumerate real
        # accounts. See login_throttle_service's module docstring for why
        # this never reaches audit_service's audit_logs table.
        account_lock_seconds = account_throttle.record_failure(email_key)
        ip_lock_seconds = ip_throttle.record_failure(ip_key)
        logger.warning(
            "login_failed",
            extra={
                "email": email_key,
                "ip": ip_key,
                "account_locked_for_seconds": round(account_lock_seconds)
                if account_lock_seconds
                else None,
                "ip_locked_for_seconds": round(ip_lock_seconds) if ip_lock_seconds else None,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Only the per-account counter clears on success -- see ip_throttle's
    # definition in login_throttle_service.py for why the per-IP one
    # deliberately never does.
    account_throttle.record_success(email_key)

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

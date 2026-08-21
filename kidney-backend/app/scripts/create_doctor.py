# app/scripts/create_doctor.py
"""Create a new doctor account.

There is no self-service /auth/register endpoint (closed 2026-08-21, see
app/api/auth.py) -- account creation is an operator-only action now. This
script is that operator action, and goes through the same service-layer
functions the old endpoint used (app/services/doctor_service.create_doctor,
app/services/hospital_service.get_or_create_hospital): passwords get hashed
the normal way, the unique-email constraint is checked first for a clean
error instead of a raw IntegrityError, and the row can't drift out of sync
with the schema the way a hand-rolled SQL INSERT with a manually computed
bcrypt hash could. It also writes the same tamper-evident audit_logs entry
any other state change in this system gets (see app/services/audit_service.py)
rather than leaving account creation invisible to the audit trail.

New accounts are never admin by default -- promote separately with
app/scripts/promote_admin.py.

Usage:
    uv run python -m app.scripts.create_doctor <email> <password> <full_name> [hospital_name]

    hospital_name defaults to "Kandy National Hospital Sri Lanka" -- the
    only hospital this system is actually deployed for today (see
    kidney-frontend's former registration form). Pass it explicitly to
    provision a doctor at any other hospital.
"""
import asyncio
import sys

from app.db.session import async_session_maker
from app.services.audit_service import create_audit_log
from app.services.doctor_service import create_doctor, get_doctor_by_email
from app.services.hospital_service import get_or_create_hospital

DEFAULT_HOSPITAL_NAME = "Kandy National Hospital Sri Lanka"
MIN_PASSWORD_LENGTH = 8


async def create_doctor_account(
    email: str,
    password: str,
    full_name: str,
    hospital_name: str = DEFAULT_HOSPITAL_NAME,
) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    async with async_session_maker() as db:
        existing = await get_doctor_by_email(db, email)
        if existing is not None:
            raise SystemExit(f"An account with email {email!r} already exists.")

        hospital = await get_or_create_hospital(db, hospital_name)
        doctor = await create_doctor(
            db, hospital_id=hospital.id, email=email, password=password, full_name=full_name
        )
        await create_audit_log(
            db,
            doctor_id=doctor.id,
            action="created_doctor",
            details={
                "email": doctor.email,
                "hospital_name": hospital_name,
                "created_via": "app.scripts.create_doctor",
            },
            commit=False,
        )
        await db.commit()
        doctor_id = doctor.id

    print(f"Created doctor account {email} (id={doctor_id}) at {hospital_name!r}.")


def main() -> None:
    if len(sys.argv) not in (4, 5):
        raise SystemExit(
            "Usage: uv run python -m app.scripts.create_doctor <email> <password> <full_name> [hospital_name]"
        )
    email, password, full_name = sys.argv[1], sys.argv[2], sys.argv[3]
    hospital_name = sys.argv[4] if len(sys.argv) == 5 else DEFAULT_HOSPITAL_NAME
    asyncio.run(create_doctor_account(email, password, full_name, hospital_name))


if __name__ == "__main__":
    main()

# app/scripts/promote_admin.py
"""Promote an existing doctor account to admin.

There is no self-service /auth/register endpoint (closed 2026-08-21, see
app/api/auth.py) and, by the same logic, no self-service admin-promotion
endpoint either -- both are operator-only, on purpose (see is_admin's own
field comment in app/models/doctor.py). This script is that operator
action: it looks a doctor up by email, flips is_admin, and writes the same
tamper-evident audit_logs entry any other state change in this system gets
(see app/services/audit_service.py) rather than silently editing the row.

This does not create accounts -- a doctor row has to exist first. Use
app/scripts/create_doctor.py to provision one.

Usage:
    uv run python -m app.scripts.promote_admin <email>
"""
import asyncio
import sys

from app.db.session import async_session_maker
from app.services.audit_service import create_audit_log
from app.services.doctor_service import get_doctor_by_email


async def promote_admin(email: str) -> None:
    async with async_session_maker() as db:
        doctor = await get_doctor_by_email(db, email)
        if doctor is None:
            raise SystemExit(f"No doctor account found for {email!r}.")

        if doctor.is_admin:
            print(f"{email} is already an admin -- nothing to do.")
            return

        doctor.is_admin = True
        await create_audit_log(
            db,
            doctor_id=doctor.id,
            action="promoted_to_admin",
            details={"email": doctor.email, "promoted_via": "app.scripts.promote_admin"},
            commit=False,
        )
        await db.commit()

    print(f"{email} is now an admin.")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: uv run python -m app.scripts.promote_admin <email>")
    asyncio.run(promote_admin(sys.argv[1]))


if __name__ == "__main__":
    main()

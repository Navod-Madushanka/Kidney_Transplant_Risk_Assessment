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

The password is never accepted as a command-line argument (B10 / Phase 3.3
of FINALIZATION-PLAN.md): anything passed on argv is visible to every other
user on the host for the life of the process via `ps`, and lands in shell
history the moment the command is entered. It's prompted for instead
(twice, since a no-echo prompt gives the operator no way to see a typo) and
checked against app/scripts/password_policy.py before the account is
created.

Usage:
    uv run python -m app.scripts.create_doctor <email> <full_name> [hospital_name]

    Prompts for the password interactively -- it is never accepted as an
    argument. hospital_name defaults to "Kandy National Hospital Sri Lanka"
    -- the only hospital this system is actually deployed for today (see
    kidney-frontend's former registration form). Pass it explicitly to
    provision a doctor at any other hospital.
"""
import asyncio
import getpass
import sys

from app.db.session import async_session_maker
from app.scripts.password_policy import validate_password_strength
from app.services.audit_service import create_audit_log
from app.services.doctor_service import create_doctor, get_doctor_by_email
from app.services.hospital_service import get_or_create_hospital

DEFAULT_HOSPITAL_NAME = "Kandy National Hospital Sri Lanka"


def _prompt_for_password() -> str:
    """Prompts twice (no-echo, via getpass) and retries on mismatch or a
    policy violation, rather than failing the whole script on the first
    typo or weak attempt -- provisioning an account is rare enough that an
    operator re-running the whole command over one mistake is real friction
    for no safety benefit."""
    while True:
        password = getpass.getpass("Password (input hidden): ")
        problems = validate_password_strength(password)
        if problems:
            print("That password is not acceptable:")
            for problem in problems:
                print(f"  - {problem}")
            print("Please try again.\n")
            continue

        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords didn't match. Please try again.\n")
            continue

        return password


async def create_doctor_account(
    email: str,
    password: str,
    full_name: str,
    hospital_name: str = DEFAULT_HOSPITAL_NAME,
) -> None:
    problems = validate_password_strength(password)
    if problems:
        raise SystemExit("Password is not acceptable: " + "; ".join(problems))

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
    if len(sys.argv) not in (3, 4):
        raise SystemExit(
            "Usage: uv run python -m app.scripts.create_doctor <email> <full_name> "
            "[hospital_name]\n"
            "(the password is prompted for interactively, not passed as an argument)"
        )
    email, full_name = sys.argv[1], sys.argv[2]
    hospital_name = sys.argv[3] if len(sys.argv) == 4 else DEFAULT_HOSPITAL_NAME
    password = _prompt_for_password()
    asyncio.run(create_doctor_account(email, password, full_name, hospital_name))


if __name__ == "__main__":
    main()

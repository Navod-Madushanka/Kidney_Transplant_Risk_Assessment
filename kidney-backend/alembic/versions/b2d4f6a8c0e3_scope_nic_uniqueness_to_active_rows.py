"""scope nic uniqueness to active (non-deleted) rows

Revision ID: b2d4f6a8c0e3
Revises: a1c3e5f7b9d1
Create Date: 2026-08-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c0e3'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Soft-deleting a donor/patient (see a1c3e5f7b9d1) didn't free up its NIC
    number: the old unique index/constraint applied to every row regardless
    of is_deleted, so re-registering a real person after their old record
    was deleted hit a false-positive "already registered" conflict. Replaces
    both with partial unique indexes that only constrain active rows.
    """
    # donors: nic_number is globally unique. Keep the plain lookup index,
    # add a partial unique index scoped to active rows.
    op.drop_index("ix_donors_nic_number", table_name="donors")
    op.create_index("ix_donors_nic_number", "donors", ["nic_number"])
    op.create_index(
        "ix_donors_nic_number_active_unique",
        "donors",
        ["nic_number"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # patients: nic_number is unique per doctor.
    op.drop_constraint(
        "uq_patients_doctor_id_nic_number", "patients", type_="unique"
    )
    op.create_index(
        "uq_patients_doctor_id_nic_number_active",
        "patients",
        ["doctor_id", "nic_number"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_patients_doctor_id_nic_number_active", table_name="patients")
    op.create_unique_constraint(
        "uq_patients_doctor_id_nic_number", "patients", ["doctor_id", "nic_number"]
    )

    op.drop_index("ix_donors_nic_number_active_unique", table_name="donors")
    op.drop_index("ix_donors_nic_number", table_name="donors")
    op.create_index("ix_donors_nic_number", "donors", ["nic_number"], unique=True)

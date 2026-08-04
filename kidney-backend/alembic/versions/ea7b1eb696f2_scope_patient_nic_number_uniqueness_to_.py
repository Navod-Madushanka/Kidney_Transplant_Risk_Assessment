"""scope patient nic_number uniqueness to per doctor

Revision ID: ea7b1eb696f2
Revises: f2b57d9a0816
Create Date: 2026-08-03 19:41:05.896951

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea7b1eb696f2'
down_revision: Union[str, Sequence[str], None] = 'f2b57d9a0816'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Patients are strictly doctor-isolated everywhere else in this codebase
    (unlike donors, which already have a deliberate cross-hospital sharing
    path) -- a global-unique nic_number contradicted that and crashed with
    an unhandled 500 the moment two different doctors' patients happened to
    share an NIC. Replace the global unique index with a plain (non-unique)
    index plus a (doctor_id, nic_number) unique constraint instead.
    """
    op.drop_index('ix_patients_nic_number', table_name='patients')
    op.create_index(op.f('ix_patients_nic_number'), 'patients', ['nic_number'], unique=False)
    op.create_unique_constraint(
        'uq_patients_doctor_id_nic_number', 'patients', ['doctor_id', 'nic_number']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_patients_doctor_id_nic_number', 'patients', type_='unique')
    op.drop_index(op.f('ix_patients_nic_number'), table_name='patients')
    op.create_index(op.f('ix_patients_nic_number'), 'patients', ['nic_number'], unique=True)

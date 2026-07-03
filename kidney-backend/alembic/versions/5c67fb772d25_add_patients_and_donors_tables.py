"""add patients and donors tables

Revision ID: 5c67fb772d25
Revises: d92e6e2feb93
Create Date: 2026-07-03 14:54:51.021553

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c67fb772d25'
down_revision: Union[str, Sequence[str], None] = 'd92e6e2feb93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


blood_type_enum = sa.Enum('O', 'A', 'B', 'AB', name='blood_type_enum')


def upgrade() -> None:
    """Upgrade schema."""
    blood_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('donors',
    sa.Column('doctor_id', sa.Uuid(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('date_of_birth', sa.Date(), nullable=False),
    sa.Column('blood_type', blood_type_enum, nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_donors_doctor_id'), 'donors', ['doctor_id'], unique=False)

    op.create_table('patients',
    sa.Column('doctor_id', sa.Uuid(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('date_of_birth', sa.Date(), nullable=False),
    sa.Column('blood_type', blood_type_enum, nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patients_doctor_id'), 'patients', ['doctor_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_patients_doctor_id'), table_name='patients')
    op.drop_table('patients')
    op.drop_index(op.f('ix_donors_doctor_id'), table_name='donors')
    op.drop_table('donors')

    blood_type_enum.drop(op.get_bind(), checkfirst=True)
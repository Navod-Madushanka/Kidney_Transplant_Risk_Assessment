"""add LKDPI inputs and result

Revision ID: b8c91b0b56bd
Revises: 7a8b6052701d
Create Date: 2026-08-10 12:00:00.000000

Adds the four new inputs Part D (LKDPI) needs -- patients.sex,
patients.weight_kg, donors.weight_kg, donors.is_biologically_related -- plus
match_reports.lkdpi_result to persist the computed score. See
app/reference_data/lkdpi_model.py for the model these feed. sex_enum already
exists (created by ae71d708307d for donors.sex), so this reuses it rather
than creating a duplicate type.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8c91b0b56bd'
down_revision: Union[str, Sequence[str], None] = '7a8b6052701d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

sex_enum = postgresql.ENUM('male', 'female', name='sex_enum')


def upgrade() -> None:
    """Upgrade schema."""
    # checkfirst=True: sex_enum was already created for donors.sex (see
    # ae71d708307d) -- this only needs to reuse it, not recreate it.
    sex_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('patients', sa.Column('sex', sex_enum, nullable=True))
    op.add_column('patients', sa.Column('weight_kg', sa.Numeric(5, 2), nullable=True))

    op.add_column('donors', sa.Column('weight_kg', sa.Numeric(5, 2), nullable=True))
    op.add_column('donors', sa.Column('is_biologically_related', sa.Boolean(), nullable=True))

    op.add_column('match_reports', sa.Column('lkdpi_result', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('match_reports', 'lkdpi_result')

    op.drop_column('donors', 'is_biologically_related')
    op.drop_column('donors', 'weight_kg')

    op.drop_column('patients', 'weight_kg')
    op.drop_column('patients', 'sex')

    # Not dropping sex_enum: donors.sex still depends on it.

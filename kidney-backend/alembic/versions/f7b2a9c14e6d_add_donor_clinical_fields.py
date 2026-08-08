"""add donor clinical fields

Revision ID: f7b2a9c14e6d
Revises: e91f3c6a2d47
Create Date: 2026-08-08 21:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7b2a9c14e6d'
down_revision: Union[str, Sequence[str], None] = 'e91f3c6a2d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('donors', sa.Column('egfr', sa.Numeric(5, 2), nullable=True))
    op.add_column('donors', sa.Column('systolic_bp', sa.Integer(), nullable=True))
    op.add_column('donors', sa.Column('diastolic_bp', sa.Integer(), nullable=True))
    op.add_column('donors', sa.Column('bmi', sa.Numeric(4, 1), nullable=True))
    op.add_column('donors', sa.Column('has_diabetes', sa.Boolean(), nullable=True))
    op.add_column('donors', sa.Column('is_smoker', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('donors', 'is_smoker')
    op.drop_column('donors', 'has_diabetes')
    op.drop_column('donors', 'bmi')
    op.drop_column('donors', 'diastolic_bp')
    op.drop_column('donors', 'systolic_bp')
    op.drop_column('donors', 'egfr')

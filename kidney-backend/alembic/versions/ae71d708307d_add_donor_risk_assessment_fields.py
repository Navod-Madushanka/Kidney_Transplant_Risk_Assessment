"""add donor risk assessment fields

Revision ID: ae71d708307d
Revises: b8f1a3d7c250
Create Date: 2026-08-09 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ae71d708307d'
down_revision: Union[str, Sequence[str], None] = 'b8f1a3d7c250'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define the PostgreSQL enum objects explicitly (see 4af62af337ff for the
# same pattern with donor_status_enum).
sex_enum = postgresql.ENUM('male', 'female', name='sex_enum')
race_enum = postgresql.ENUM('black', 'white', 'other', name='race_enum')
smoking_status_enum = postgresql.ENUM('never', 'former', 'current', name='smoking_status_enum')


def upgrade() -> None:
    """Upgrade schema."""
    sex_enum.create(op.get_bind(), checkfirst=True)
    race_enum.create(op.get_bind(), checkfirst=True)
    smoking_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('donors', sa.Column('sex', sex_enum, nullable=True))
    op.add_column('donors', sa.Column('race', race_enum, nullable=True))
    op.add_column('donors', sa.Column('smoking_status', smoking_status_enum, nullable=True))
    op.add_column('donors', sa.Column('creatinine', sa.Numeric(4, 2), nullable=True))
    op.add_column('donors', sa.Column('urine_acr', sa.Numeric(8, 2), nullable=True))
    op.add_column(
        'donors', sa.Column('is_on_antihypertensive_medication', sa.Boolean(), nullable=True)
    )
    op.add_column(
        'donors', sa.Column('family_history_kidney_disease', sa.Boolean(), nullable=True)
    )

    # is_smoker (bool) -> smoking_status (never/former/current): a bare
    # `True` is ambiguous between "former" and "current", so there's no
    # lossless conversion. Dropped rather than backfilled -- existing rows
    # start with smoking_status = NULL (unknown) instead of a guessed value.
    op.drop_column('donors', 'is_smoker')


def downgrade() -> None:
    """Downgrade schema."""
    # Data loss: smoking_status values aren't recoverable as is_smoker.
    op.add_column('donors', sa.Column('is_smoker', sa.Boolean(), nullable=True))

    op.drop_column('donors', 'family_history_kidney_disease')
    op.drop_column('donors', 'is_on_antihypertensive_medication')
    op.drop_column('donors', 'urine_acr')
    op.drop_column('donors', 'creatinine')
    op.drop_column('donors', 'smoking_status')
    op.drop_column('donors', 'race')
    op.drop_column('donors', 'sex')

    smoking_status_enum.drop(op.get_bind(), checkfirst=True)
    race_enum.drop(op.get_bind(), checkfirst=True)
    sex_enum.drop(op.get_bind(), checkfirst=True)

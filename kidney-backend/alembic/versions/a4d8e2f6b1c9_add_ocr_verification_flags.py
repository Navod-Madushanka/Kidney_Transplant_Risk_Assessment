"""add ocr verification flags

Revision ID: a4d8e2f6b1c9
Revises: f7b2a9c14e6d
Create Date: 2026-08-08 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4d8e2f6b1c9'
down_revision: Union[str, Sequence[str], None] = 'f7b2a9c14e6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default='true' -- every pre-existing row predates this feature
    # entirely, so there's no way to know in hindsight whether its data came
    # from OCR or manual entry. Defaulting to trusted (rather than retroactively
    # blocking every existing patient/donor from a new compatibility check)
    # matches how donor status/clinical-field migrations in this same batch
    # treat pre-existing rows.
    op.add_column(
        'patients',
        sa.Column('hla_typing_verified', sa.Boolean(), nullable=False, server_default='true'),
    )
    op.add_column(
        'patients',
        sa.Column('antibody_profile_verified', sa.Boolean(), nullable=False, server_default='true'),
    )
    op.add_column(
        'donors',
        sa.Column('hla_typing_verified', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('donors', 'hla_typing_verified')
    op.drop_column('patients', 'antibody_profile_verified')
    op.drop_column('patients', 'hla_typing_verified')

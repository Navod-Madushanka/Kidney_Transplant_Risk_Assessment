"""add details_verified flag

Revision ID: e5c9a2f4d8b7
Revises: d4f8b1a3c6e9
Create Date: 2026-08-09 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5c9a2f4d8b7'
down_revision: Union[str, Sequence[str], None] = 'd4f8b1a3c6e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Review #2 bug 6: blood_type/date_of_birth are OCR-extractable same as
    HLA typing (see PersonDetailsOcr) but had no verification concept at
    all -- see the matching column comment on app/models/patient.py.
    server_default='true' -- every pre-existing row predates this feature,
    so defaulting to trusted (not retroactively blocking every existing
    patient/donor) matches how a4d8e2f6b1c9 treated the same situation for
    hla_typing_verified/antibody_profile_verified.
    """
    op.add_column(
        'patients',
        sa.Column('details_verified', sa.Boolean(), nullable=False, server_default='true'),
    )
    op.add_column(
        'donors',
        sa.Column('details_verified', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('donors', 'details_verified')
    op.drop_column('patients', 'details_verified')

"""add is_admin to doctors

Revision ID: f1a6c9e3b7d2
Revises: e5c9a2f4d8b7
Create Date: 2026-08-09 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a6c9e3b7d2'
down_revision: Union[str, Sequence[str], None] = 'e5c9a2f4d8b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Review #2 bug 12: /audit-logs/verify (and the GET /audit-logs list
    route added alongside it) had nothing tighter than "any authenticated
    doctor" to gate on -- there was no role/permission concept in this
    data model at all. server_default='false' -- no pre-existing doctor
    account should silently become an admin; promoting one is a deliberate
    operator action (set this column directly in the database), not
    something this migration should do on anyone's behalf.
    """
    op.add_column(
        'doctors',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('doctors', 'is_admin')

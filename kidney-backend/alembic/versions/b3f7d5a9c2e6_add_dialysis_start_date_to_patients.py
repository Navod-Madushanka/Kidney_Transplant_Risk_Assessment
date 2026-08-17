"""add dialysis_start_date to patients

Revision ID: b3f7d5a9c2e6
Revises: d1f4b7e2a936
Create Date: 2026-08-16 00:00:00.000000

K9: exchange_weight_policies.py's _wait_fraction previously had only
Patient.created_at (registration date) as a waiting-time proxy -- time on
dialysis, not time in this database, is what real allocation systems credit.
Nullable so old records keep working; _wait_fraction falls back to
created_at when this is unset and discloses the fallback in the response.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f7d5a9c2e6'
down_revision: Union[str, Sequence[str], None] = 'd1f4b7e2a936'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('patients', sa.Column('dialysis_start_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('patients', 'dialysis_start_date')

"""add status to donors

Revision ID: 4af62af337ff
Revises: f4a8c1d92b3e
Create Date: 2026-08-01 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4af62af337ff'
down_revision: Union[str, Sequence[str], None] = 'f4a8c1d92b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define the PostgreSQL enum object explicitly
donor_status_enum = postgresql.ENUM('available', 'reserved', 'transplanted', name='donor_status_enum')


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create the enum type in PostgreSQL (if not created yet)
    donor_status_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add column as nullable first so existing rows don't break
    op.add_column('donors', sa.Column('status', donor_status_enum, nullable=True))

    # 3. Populate existing rows with a default value
    op.execute("UPDATE donors SET status = 'available' WHERE status IS NULL")

    # 4. Now safely enforce NOT NULL constraint
    op.alter_column('donors', 'status', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Drop the column first
    op.drop_column('donors', 'status')

    # 2. Drop the enum type from PostgreSQL
    donor_status_enum.drop(op.get_bind(), checkfirst=True)

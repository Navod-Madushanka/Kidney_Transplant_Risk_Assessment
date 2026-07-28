"""add rh_factor to patients and donors

Revision ID: dc15cf72e93b
Revises: 8720582dd3e4
Create Date: 2026-07-28 09:43:28.578872

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'dc15cf72e93b'
down_revision: Union[str, Sequence[str], None] = '8720582dd3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define the PostgreSQL enum object explicitly
rh_factor_enum = postgresql.ENUM('+', '-', name='rh_factor_enum')


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create the enum type in PostgreSQL (if not created yet)
    rh_factor_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add column as nullable first so existing rows don't break
    op.add_column('patients', sa.Column('rh_factor', rh_factor_enum, nullable=True))
    op.add_column('donors', sa.Column('rh_factor', rh_factor_enum, nullable=True))

    # 3. Populate existing rows with a default value (e.g., '+')
    op.execute("UPDATE patients SET rh_factor = '+' WHERE rh_factor IS NULL")
    op.execute("UPDATE donors SET rh_factor = '+' WHERE rh_factor IS NULL")

    # 4. Now safely enforce NOT NULL constraint
    op.alter_column('patients', 'rh_factor', nullable=False)
    op.alter_column('donors', 'rh_factor', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Drop the columns first
    op.drop_column('donors', 'rh_factor')
    op.drop_column('patients', 'rh_factor')

    # 2. Drop the enum type from PostgreSQL
    rh_factor_enum.drop(op.get_bind(), checkfirst=True)
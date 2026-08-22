"""add reference_versions to match_reports

Revision ID: c8a1f4e6b3d0
Revises: e2c6b8a4f1d3
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'c8a1f4e6b3d0'
down_revision: Union[str, Sequence[str], None] = 'e2c6b8a4f1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds the nullable reference_versions JSONB column (see
    app.reference_data.versions.CLINICAL_REFERENCE_VERSIONS and
    MatchReport.reference_versions). No backfill: pre-existing rows are
    simply left null rather than guessed at, same precedent as
    lkdpi_result (b8c91b0b56bd) -- unlike outcome (7a8b6052701d), there is
    no way to recompute after the fact which reference-data version was
    actually in force when an old report was generated.
    """
    op.add_column('match_reports', sa.Column('reference_versions', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('match_reports', 'reference_versions')

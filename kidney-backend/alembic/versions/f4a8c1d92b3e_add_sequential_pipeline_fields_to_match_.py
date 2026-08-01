"""add sequential pipeline fields to match_reports

Revision ID: f4a8c1d92b3e
Revises: dc15cf72e93b
Create Date: 2026-07-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f4a8c1d92b3e'
down_revision: Union[str, Sequence[str], None] = 'dc15cf72e93b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # New columns for the Step 1-7 sequential pipeline (roadmap Phase 3):
    # mismatch_result/pra_bucket_result are Steps 3 and 4, crossmatch_result
    # is Step 6, final_risk_level is the Step 7 classification. All
    # nullable — existing rows predate this pipeline and never ran these
    # steps, and even new rows may halt before reaching some of them.
    op.add_column('match_reports', sa.Column('mismatch_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('match_reports', sa.Column('pra_bucket_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('match_reports', sa.Column('crossmatch_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('match_reports', sa.Column('final_risk_level', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('match_reports', 'final_risk_level')
    op.drop_column('match_reports', 'crossmatch_result')
    op.drop_column('match_reports', 'pra_bucket_result')
    op.drop_column('match_reports', 'mismatch_result')

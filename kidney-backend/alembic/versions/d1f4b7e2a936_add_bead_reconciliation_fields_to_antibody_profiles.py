"""add bead reconciliation fields to antibody_profiles

Revision ID: d1f4b7e2a936
Revises: a8f3c6d1e9b4
Create Date: 2026-08-15 10:00:00.000000

Part I (bead-row identity / tile reconciliation): the source bead-
specificity chart carries its own row identity (a 3-digit Bead code,
unique within one page's panel) that the extraction pipeline used to
discard entirely -- see ocr-service's bead_reconciliation.py module
docstring for why keying on (antigen, mfi) instead silently created
duplicate rows and dropped real ones.

All three columns are nullable and this migration adds them only -- no
backfill, per the plan: there is no source to backfill an existing row's
bead_id/panel from, and a row transcribed by hand (or one that predates
this column) genuinely has neither. Existing rows keep NULLs, the honest
representation.

Deliberately NOT adding a uniqueness constraint on (patient_id, panel,
bead_id) in this migration -- see the Part I plan's I10: added too early,
before reconciliation has run in production long enough to trust it, it
would convert a silent double-count into a failed job instead. Add that
index in a follow-up once the real conflict rate is known.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd1f4b7e2a936'
down_revision: Union[str, Sequence[str], None] = 'a8f3c6d1e9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    antibody_panel_enum = sa.Enum('class_i', 'class_ii', name='antibody_panel_enum')
    antibody_panel_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('antibody_profiles', sa.Column('bead_id', sa.String(length=3), nullable=True))
    op.add_column(
        'antibody_profiles', sa.Column('panel', antibody_panel_enum, nullable=True)
    )
    op.add_column(
        'antibody_profiles',
        sa.Column('extraction_conflict', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('antibody_profiles', 'extraction_conflict')
    op.drop_column('antibody_profiles', 'panel')
    op.drop_column('antibody_profiles', 'bead_id')

    antibody_panel_enum = sa.Enum('class_i', 'class_ii', name='antibody_panel_enum')
    antibody_panel_enum.drop(op.get_bind(), checkfirst=True)

"""add intended recipient to donors

Revision ID: b8f1a3d7c250
Revises: a4d8e2f6b1c9
Create Date: 2026-08-09 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8f1a3d7c250'
down_revision: Union[str, Sequence[str], None] = 'a4d8e2f6b1c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('donors', sa.Column('intended_recipient_id', sa.Uuid(), nullable=True))
    op.create_index(
        op.f('ix_donors_intended_recipient_id'), 'donors', ['intended_recipient_id']
    )
    op.create_foreign_key(
        'fk_donors_intended_recipient_id_patients',
        'donors',
        'patients',
        ['intended_recipient_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_donors_intended_recipient_id_patients', 'donors', type_='foreignkey')
    op.drop_index(op.f('ix_donors_intended_recipient_id'), table_name='donors')
    op.drop_column('donors', 'intended_recipient_id')

"""add exchange_proposals and exchange_proposal_pairs tables

Revision ID: e2c6b8a4f1d3
Revises: b3f7d5a9c2e6
Create Date: 2026-08-16 00:00:00.000000

Part K, K2/K3: the paired-exchange commitment workflow. exchange_proposals
snapshots a discovered cycle (mirrors MatchReport's JSONB-snapshot
convention); exchange_proposal_pairs is one row per pair in that cycle, and
its partial unique index on donor_id WHERE is_open is the actual overlap
invariant -- a donor may be in at most one open proposal system-wide,
enforced by Postgres, not application code alone.

Pre-production, no real data to preserve: clean create.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB

# revision identifiers, used by Alembic.
revision: str = 'e2c6b8a4f1d3'
down_revision: Union[str, Sequence[str], None] = 'b3f7d5a9c2e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


exchange_proposal_status_enum = ENUM(
    'proposed', 'accepted', 'declined', 'expired', 'cancelled', 'completed',
    name='exchange_proposal_status_enum',
    create_type=False,
)
exchange_proposal_pair_decision_enum = ENUM(
    'pending', 'accepted', 'declined',
    name='exchange_proposal_pair_decision_enum',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    exchange_proposal_status_enum.create(op.get_bind(), checkfirst=True)
    exchange_proposal_pair_decision_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'exchange_proposals',
        sa.Column('created_by_doctor_id', sa.Uuid(), nullable=False),
        sa.Column('policy', sa.String(length=50), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column(
            'status', exchange_proposal_status_enum, server_default='proposed', nullable=False
        ),
        sa.Column('cycle_snapshot', JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['created_by_doctor_id'], ['doctors.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_exchange_proposals_created_by_doctor_id'),
        'exchange_proposals', ['created_by_doctor_id'], unique=False,
    )

    op.create_table(
        'exchange_proposal_pairs',
        sa.Column('proposal_id', sa.Uuid(), nullable=False),
        sa.Column('donor_id', sa.Uuid(), nullable=False),
        sa.Column('patient_id', sa.Uuid(), nullable=False),
        sa.Column('owning_doctor_id', sa.Uuid(), nullable=False),
        sa.Column(
            'decision', exchange_proposal_pair_decision_enum, server_default='pending', nullable=False
        ),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_by_doctor_id', sa.Uuid(), nullable=True),
        sa.Column('decline_reason', sa.String(length=500), nullable=True),
        sa.Column('is_open', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['proposal_id'], ['exchange_proposals.id']),
        sa.ForeignKeyConstraint(['donor_id'], ['donors.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.ForeignKeyConstraint(['owning_doctor_id'], ['doctors.id']),
        sa.ForeignKeyConstraint(['decided_by_doctor_id'], ['doctors.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_exchange_proposal_pairs_proposal_id'),
        'exchange_proposal_pairs', ['proposal_id'], unique=False,
    )
    op.create_index(
        op.f('ix_exchange_proposal_pairs_donor_id'),
        'exchange_proposal_pairs', ['donor_id'], unique=False,
    )
    op.create_index(
        op.f('ix_exchange_proposal_pairs_patient_id'),
        'exchange_proposal_pairs', ['patient_id'], unique=False,
    )
    op.create_index(
        op.f('ix_exchange_proposal_pairs_owning_doctor_id'),
        'exchange_proposal_pairs', ['owning_doctor_id'], unique=False,
    )
    op.create_index(
        'ix_exchange_proposal_pairs_donor_id_open_unique',
        'exchange_proposal_pairs',
        ['donor_id'],
        unique=True,
        postgresql_where=sa.text('is_open'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_exchange_proposal_pairs_donor_id_open_unique', table_name='exchange_proposal_pairs'
    )
    op.drop_index(
        op.f('ix_exchange_proposal_pairs_owning_doctor_id'), table_name='exchange_proposal_pairs'
    )
    op.drop_index(
        op.f('ix_exchange_proposal_pairs_patient_id'), table_name='exchange_proposal_pairs'
    )
    op.drop_index(
        op.f('ix_exchange_proposal_pairs_donor_id'), table_name='exchange_proposal_pairs'
    )
    op.drop_index(
        op.f('ix_exchange_proposal_pairs_proposal_id'), table_name='exchange_proposal_pairs'
    )
    op.drop_table('exchange_proposal_pairs')

    op.drop_index(
        op.f('ix_exchange_proposals_created_by_doctor_id'), table_name='exchange_proposals'
    )
    op.drop_table('exchange_proposals')

    exchange_proposal_pair_decision_enum.drop(op.get_bind(), checkfirst=True)
    exchange_proposal_status_enum.drop(op.get_bind(), checkfirst=True)

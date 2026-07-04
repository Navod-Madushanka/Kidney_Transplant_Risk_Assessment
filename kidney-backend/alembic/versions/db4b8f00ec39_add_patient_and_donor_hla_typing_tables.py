"""add patient and donor hla typing tables

Revision ID: db4b8f00ec39
Revises: 5c67fb772d25
Create Date: 2026-07-04 09:07:33.552695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision: str = 'db4b8f00ec39'
down_revision: Union[str, Sequence[str], None] = '5c67fb772d25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


hla_locus_enum = ENUM(
    'DRB1', 'B', 'DQB1', 'C', 'A', 'DRB3,4,5', 'DQA1', 'DPA1', 'DPB1',
    name='hla_locus_enum',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    hla_locus_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('donor_hla_typings',
    sa.Column('donor_id', sa.Uuid(), nullable=False),
    sa.Column('locus', hla_locus_enum, nullable=False),
    sa.Column('allele_1', sa.String(), nullable=False),
    sa.Column('allele_2', sa.String(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('donor_id', 'locus')
    )
    op.create_index(op.f('ix_donor_hla_typings_donor_id'), 'donor_hla_typings', ['donor_id'], unique=False)

    op.create_table('patient_hla_typings',
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('locus', hla_locus_enum, nullable=False),
    sa.Column('allele_1', sa.String(), nullable=False),
    sa.Column('allele_2', sa.String(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('patient_id', 'locus')
    )
    op.create_index(op.f('ix_patient_hla_typings_patient_id'), 'patient_hla_typings', ['patient_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_patient_hla_typings_patient_id'), table_name='patient_hla_typings')
    op.drop_table('patient_hla_typings')
    op.drop_index(op.f('ix_donor_hla_typings_donor_id'), table_name='donor_hla_typings')
    op.drop_table('donor_hla_typings')

    hla_locus_enum.drop(op.get_bind(), checkfirst=True)
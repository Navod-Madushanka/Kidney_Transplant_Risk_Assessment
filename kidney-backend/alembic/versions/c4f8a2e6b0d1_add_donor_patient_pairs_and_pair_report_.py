"""add donor_patient_pairs and pair_report_files tables

Revision ID: c4f8a2e6b0d1
Revises: b8c91b0b56bd
Create Date: 2026-08-11 12:00:00.000000

Two of the three lab documents this system consumes (HLA typing report,
crossmatch report) actually cover a patient and donor together, not one
person -- see PairReportFile. donor_patient_pairs is the new owner for
those two documents and for the crossmatch transcription; it is additive
storage on top of Donor.intended_recipient_id (still authoritative for the
matching engine), not a replacement for it -- see both models' docstrings.

Pre-production, no real data to preserve: this is a clean create, no
backfill from existing patient_report_files/donor_report_files rows or from
donors.intended_recipient_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = 'c4f8a2e6b0d1'
down_revision: Union[str, Sequence[str], None] = 'b8c91b0b56bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


report_file_category_enum = ENUM(
    'hla_typing_report',
    'crossmatch_report',
    'bead_specificity_chart_page_1',
    'bead_specificity_chart_page_2',
    'other',
    name='report_file_category_enum',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'donor_patient_pairs',
        sa.Column('doctor_id', sa.Uuid(), nullable=False),
        sa.Column('patient_id', sa.Uuid(), nullable=False),
        sa.Column('donor_id', sa.Uuid(), nullable=False),
        sa.Column('crossmatch_t_cell_result', sa.String(length=50), nullable=True),
        sa.Column('crossmatch_b_cell_result', sa.String(length=50), nullable=True),
        sa.Column('crossmatch_interpretation', sa.Text(), nullable=True),
        sa.Column('crossmatch_remarks', sa.Text(), nullable=True),
        sa.Column('crossmatch_test_date', sa.Date(), nullable=True),
        sa.Column(
            'crossmatch_verified', sa.Boolean(), server_default='true', nullable=False
        ),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.ForeignKeyConstraint(['donor_id'], ['donors.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_donor_patient_pairs_doctor_id'), 'donor_patient_pairs', ['doctor_id'], unique=False
    )
    op.create_index(
        op.f('ix_donor_patient_pairs_patient_id'), 'donor_patient_pairs', ['patient_id'], unique=False
    )
    op.create_index(
        op.f('ix_donor_patient_pairs_donor_id'), 'donor_patient_pairs', ['donor_id'], unique=False
    )
    op.create_index(
        'ix_donor_patient_pairs_patient_id_donor_id_active_unique',
        'donor_patient_pairs',
        ['patient_id', 'donor_id'],
        unique=True,
        postgresql_where=sa.text('is_deleted = false'),
    )

    op.create_table(
        'pair_report_files',
        sa.Column('pair_id', sa.Uuid(), nullable=False),
        sa.Column('category', report_file_category_enum, nullable=False),
        sa.Column('original_filename', sa.String(), nullable=False),
        sa.Column('storage_path', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['pair_id'], ['donor_patient_pairs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('storage_path'),
        sa.UniqueConstraint('pair_id', 'category', name='uq_pair_report_files_pair_id_category'),
    )
    op.create_index(
        op.f('ix_pair_report_files_pair_id'), 'pair_report_files', ['pair_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_pair_report_files_pair_id'), table_name='pair_report_files')
    op.drop_table('pair_report_files')

    op.drop_index(
        'ix_donor_patient_pairs_patient_id_donor_id_active_unique',
        table_name='donor_patient_pairs',
    )
    op.drop_index(op.f('ix_donor_patient_pairs_donor_id'), table_name='donor_patient_pairs')
    op.drop_index(op.f('ix_donor_patient_pairs_patient_id'), table_name='donor_patient_pairs')
    op.drop_index(op.f('ix_donor_patient_pairs_doctor_id'), table_name='donor_patient_pairs')
    op.drop_table('donor_patient_pairs')

"""add patient and donor report file tables

Revision ID: f2b57d9a0816
Revises: 4af62af337ff
Create Date: 2026-08-01 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision: str = 'f2b57d9a0816'
down_revision: Union[str, Sequence[str], None] = '4af62af337ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


report_file_category_enum = ENUM(
    'hla_typing_report', 'crossmatch_report', 'bead_specificity_chart', 'other',
    name='report_file_category_enum',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    report_file_category_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('donor_report_files',
    sa.Column('donor_id', sa.Uuid(), nullable=False),
    sa.Column('category', report_file_category_enum, nullable=False),
    sa.Column('original_filename', sa.String(), nullable=False),
    sa.Column('storage_path', sa.String(), nullable=False),
    sa.Column('content_type', sa.String(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_path')
    )
    op.create_index(op.f('ix_donor_report_files_donor_id'), 'donor_report_files', ['donor_id'], unique=False)

    op.create_table('patient_report_files',
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('category', report_file_category_enum, nullable=False),
    sa.Column('original_filename', sa.String(), nullable=False),
    sa.Column('storage_path', sa.String(), nullable=False),
    sa.Column('content_type', sa.String(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_path')
    )
    op.create_index(op.f('ix_patient_report_files_patient_id'), 'patient_report_files', ['patient_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_patient_report_files_patient_id'), table_name='patient_report_files')
    op.drop_table('patient_report_files')
    op.drop_index(op.f('ix_donor_report_files_donor_id'), table_name='donor_report_files')
    op.drop_table('donor_report_files')

    report_file_category_enum.drop(op.get_bind(), checkfirst=True)

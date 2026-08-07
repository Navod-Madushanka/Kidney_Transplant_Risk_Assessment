"""add ocr extraction jobs table

Revision ID: 73b76de93588
Revises: b2d4f6a8c0e3
Create Date: 2026-08-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '73b76de93588'
down_revision: Union[str, Sequence[str], None] = 'b2d4f6a8c0e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ocr_extraction_job_status_enum = postgresql.ENUM(
    'running', 'done', 'failed', name='ocr_extraction_job_status_enum',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    ocr_extraction_job_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('ocr_extraction_jobs',
    sa.Column('doctor_id', sa.Uuid(), nullable=False),
    sa.Column('status', ocr_extraction_job_status_enum, nullable=False, server_default='running'),
    sa.Column('documents', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ocr_extraction_jobs_doctor_id'), 'ocr_extraction_jobs', ['doctor_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ocr_extraction_jobs_doctor_id'), table_name='ocr_extraction_jobs')
    op.drop_table('ocr_extraction_jobs')
    ocr_extraction_job_status_enum.drop(op.get_bind(), checkfirst=True)

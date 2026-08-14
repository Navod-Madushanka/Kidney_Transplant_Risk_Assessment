"""add patient_id to ocr_extraction_jobs

Revision ID: a8f3c6d1e9b4
Revises: c4f8a2e6b0d1
Create Date: 2026-08-14 09:00:00.000000

Registration-time bead-specificity extraction (see NewPairPage.jsx) starts a
job against a patient that already exists, unlike the compatibility-check
wizard's own Photos-step jobs, which start before a patient is even selected
(wizard route order is photos -> subject -> ...). Nullable: only the new
registration-time call path ever sets this -- see
ocr_job_service.run_extraction_job, which uses it to auto-save extracted
bead-specificity rows to antibody_profiles (unverified) once the job
finishes, since nobody is necessarily still watching the wizard to do that
save themselves.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a8f3c6d1e9b4'
down_revision: Union[str, Sequence[str], None] = 'c4f8a2e6b0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ocr_extraction_jobs', sa.Column('patient_id', sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        'fk_ocr_extraction_jobs_patient_id_patients',
        'ocr_extraction_jobs',
        'patients',
        ['patient_id'],
        ['id'],
    )
    op.create_index(
        op.f('ix_ocr_extraction_jobs_patient_id'),
        'ocr_extraction_jobs',
        ['patient_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ocr_extraction_jobs_patient_id'), table_name='ocr_extraction_jobs')
    op.drop_constraint(
        'fk_ocr_extraction_jobs_patient_id_patients', 'ocr_extraction_jobs', type_='foreignkey'
    )
    op.drop_column('ocr_extraction_jobs', 'patient_id')

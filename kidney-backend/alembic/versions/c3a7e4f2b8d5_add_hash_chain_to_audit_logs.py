"""add hash chain to audit_logs

Revision ID: c3a7e4f2b8d5
Revises: 4b8e2c6f9a17
Create Date: 2026-08-08 20:00:00.000000

"""
import hashlib
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3a7e4f2b8d5'
down_revision: Union[str, Sequence[str], None] = '4b8e2c6f9a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deliberately copied from app.services.audit_service rather than imported:
# migrations must keep producing the same result years from now even if the
# live hash formula there ever changes, so this backfill is frozen in place
# rather than tracking that module.
GENESIS_HASH = "0" * 64


def _compute_audit_hash(prev_hash, doctor_id, patient_id, donor_id, action, created_at, details) -> str:
    payload = "|".join(
        [
            prev_hash,
            str(doctor_id),
            str(patient_id) if patient_id is not None else "",
            str(donor_id) if donor_id is not None else "",
            action,
            created_at.isoformat(),
            json.dumps(details, sort_keys=True, default=str) if details is not None else "null",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add both columns as nullable first so existing rows don't break.
    op.add_column('audit_logs', sa.Column('prev_hash', sa.String(length=64), nullable=True))
    op.add_column('audit_logs', sa.Column('hash', sa.String(length=64), nullable=True))

    # 2. Backfill any existing rows into a chain, oldest first, using the
    # exact same formula create_audit_log() uses going forward.
    bind = op.get_bind()
    existing_rows = bind.execute(
        sa.text(
            "SELECT id, doctor_id, patient_id, donor_id, action, created_at, details "
            "FROM audit_logs ORDER BY created_at ASC, id ASC"
        )
    ).fetchall()

    prev_hash = GENESIS_HASH
    for row in existing_rows:
        row_hash = _compute_audit_hash(
            prev_hash, row.doctor_id, row.patient_id, row.donor_id,
            row.action, row.created_at, row.details,
        )
        bind.execute(
            sa.text("UPDATE audit_logs SET prev_hash = :prev_hash, hash = :hash WHERE id = :id"),
            {"prev_hash": prev_hash, "hash": row_hash, "id": row.id},
        )
        prev_hash = row_hash

    # 3. Now safely enforce NOT NULL + uniqueness on hash.
    op.alter_column('audit_logs', 'prev_hash', nullable=False)
    op.alter_column('audit_logs', 'hash', nullable=False)
    op.create_index(op.f('ix_audit_logs_hash'), 'audit_logs', ['hash'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_audit_logs_hash'), table_name='audit_logs')
    op.drop_column('audit_logs', 'hash')
    op.drop_column('audit_logs', 'prev_hash')

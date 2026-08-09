"""add id to audit hash digest

Revision ID: a9d3f6c1b8e4
Revises: f1a6c9e3b7d2
Create Date: 2026-08-09 20:00:00.000000

"""
import hashlib
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9d3f6c1b8e4'
down_revision: Union[str, Sequence[str], None] = 'f1a6c9e3b7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deliberately copied from app.services.audit_service rather than imported
# -- see c3a7e4f2b8d5's identical comment on why this stays frozen. Adds
# `id` to the payload, joined at the end (review #2 bug 16): without it, an
# UPDATE that swapped two rows' primary keys (or reassigned one to an
# arbitrary value) touched no hashed field and verification still passed.
GENESIS_HASH = "0" * 64


def _compute_audit_hash(prev_hash, doctor_id, patient_id, donor_id, action, created_at, details, row_id) -> str:
    payload = "|".join(
        [
            prev_hash,
            str(doctor_id),
            str(patient_id) if patient_id is not None else "",
            str(donor_id) if donor_id is not None else "",
            action,
            created_at.isoformat(),
            json.dumps(details, sort_keys=True, default=str) if details is not None else "null",
            str(row_id),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upgrade() -> None:
    """Upgrade schema.

    Recomputes every existing row's hash/prev_hash chain with the new
    (id-inclusive) formula, walking oldest-first by seq -- the same
    reliable, clock-independent order create_audit_log/verify_audit_chain
    now use (see d4f8b1a3c6e9). This is a live-data backfill, not a schema
    change: no columns added or dropped.
    """
    bind = op.get_bind()
    existing_rows = bind.execute(
        sa.text(
            "SELECT id, doctor_id, patient_id, donor_id, action, created_at, details "
            "FROM audit_logs ORDER BY seq ASC"
        )
    ).fetchall()

    prev_hash = GENESIS_HASH
    for row in existing_rows:
        row_hash = _compute_audit_hash(
            prev_hash, row.doctor_id, row.patient_id, row.donor_id,
            row.action, row.created_at, row.details, row.id,
        )
        bind.execute(
            sa.text("UPDATE audit_logs SET prev_hash = :prev_hash, hash = :hash WHERE id = :id"),
            {"prev_hash": prev_hash, "hash": row_hash, "id": row.id},
        )
        prev_hash = row_hash


def downgrade() -> None:
    """Upgrade schema.

    Not reversible: the pre-image hash values aren't retained anywhere (the
    same one-way tradeoff c3a7e4f2b8d5 made). A downgrade would need to
    recompute the OLD (id-less) formula from scratch, which is possible in
    principle but not implemented here -- there's no operational reason to
    downgrade past this migration; re-run the upgrade's logic with the old
    formula by hand if it's ever genuinely needed.
    """
    raise NotImplementedError(
        "This migration's data backfill is not reversible -- see downgrade()'s docstring."
    )

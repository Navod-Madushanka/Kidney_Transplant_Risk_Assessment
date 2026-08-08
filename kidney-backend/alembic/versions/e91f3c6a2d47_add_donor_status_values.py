"""add donor status values

Revision ID: e91f3c6a2d47
Revises: c3a7e4f2b8d5
Create Date: 2026-08-08 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e91f3c6a2d47'
down_revision: Union[str, Sequence[str], None] = 'c3a7e4f2b8d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_VALUES = ("under_workup", "medically_unfit", "withdrawn", "deceased")


def upgrade() -> None:
    """Upgrade schema."""
    # Purely additive -- ADD VALUE is transactional on Postgres 12+ as long
    # as the new value isn't used by other DML in the same transaction
    # (it isn't here), so this doesn't need the full type-recreation dance
    # 4b8e2c6f9a17 used for a rename/removal.
    for value in _NEW_VALUES:
        op.execute(f"ALTER TYPE donor_status_enum ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    """Downgrade schema.

    Postgres has no ADD VALUE inverse (no DROP VALUE), so this rebuilds the
    original 3-value type the same way 4b8e2c6f9a17 rebuilds
    report_file_category_enum: any donor actually left in one of the four
    new statuses is reset to 'available' first (documented, deliberate
    choice -- there's no lossless mapping back to the old 3 values) so the
    column can be repointed at a type that doesn't have room for them.
    """
    op.execute(f"""
        UPDATE donors SET status = 'available'
        WHERE status::text IN ({", ".join(f"'{v}'" for v in _NEW_VALUES)})
    """)

    op.execute("""
        CREATE TYPE donor_status_enum_old AS ENUM (
            'available', 'reserved', 'transplanted'
        )
    """)
    op.execute("""
        ALTER TABLE donors
        ALTER COLUMN status TYPE donor_status_enum_old
        USING (status::text)::donor_status_enum_old
    """)
    op.execute("DROP TYPE donor_status_enum")
    op.execute("ALTER TYPE donor_status_enum_old RENAME TO donor_status_enum")

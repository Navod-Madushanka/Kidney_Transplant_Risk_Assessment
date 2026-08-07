"""one report file per category

Revision ID: 9d3f5b1a7c42
Revises: 73b76de93588
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '9d3f5b1a7c42'
down_revision: Union[str, Sequence[str], None] = '73b76de93588'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Each patient/donor now has at most one report file per category (the
    frontend presents 4 dedicated slots instead of an open-ended list), so
    re-uploading to a filled slot replaces the existing row. Before adding
    the constraint, drop any pre-existing duplicates, keeping only the most
    recently uploaded file per (entity_id, category).
    """
    op.execute("""
        DELETE FROM patient_report_files a
        USING patient_report_files b
        WHERE a.patient_id = b.patient_id
          AND a.category = b.category
          AND a.created_at < b.created_at
    """)
    op.execute("""
        DELETE FROM patient_report_files a
        USING patient_report_files b
        WHERE a.patient_id = b.patient_id
          AND a.category = b.category
          AND a.id < b.id
          AND a.created_at = b.created_at
    """)
    op.execute("""
        DELETE FROM donor_report_files a
        USING donor_report_files b
        WHERE a.donor_id = b.donor_id
          AND a.category = b.category
          AND a.created_at < b.created_at
    """)
    op.execute("""
        DELETE FROM donor_report_files a
        USING donor_report_files b
        WHERE a.donor_id = b.donor_id
          AND a.category = b.category
          AND a.id < b.id
          AND a.created_at = b.created_at
    """)

    op.create_unique_constraint(
        "uq_patient_report_files_patient_id_category",
        "patient_report_files",
        ["patient_id", "category"],
    )
    op.create_unique_constraint(
        "uq_donor_report_files_donor_id_category",
        "donor_report_files",
        ["donor_id", "category"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_donor_report_files_donor_id_category", "donor_report_files", type_="unique"
    )
    op.drop_constraint(
        "uq_patient_report_files_patient_id_category", "patient_report_files", type_="unique"
    )

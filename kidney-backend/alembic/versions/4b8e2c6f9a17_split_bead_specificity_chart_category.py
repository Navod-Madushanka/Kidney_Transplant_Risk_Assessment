"""split bead specificity chart category into page 1 and page 2

Revision ID: 4b8e2c6f9a17
Revises: 9d3f5b1a7c42
Create Date: 2026-08-07 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4b8e2c6f9a17'
down_revision: Union[str, Sequence[str], None] = '9d3f5b1a7c42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Postgres can't rename/remove enum values transactionally the easy way, so
# this recreates the type: build the new enum, repoint both tables' category
# columns at it (mapping the old single "bead_specificity_chart" value to
# "..._page_1"), then drop the old type and rename the new one into its place.
_TABLES = ("patient_report_files", "donor_report_files")


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TYPE report_file_category_enum_new AS ENUM (
            'hla_typing_report', 'crossmatch_report',
            'bead_specificity_chart_page_1', 'bead_specificity_chart_page_2',
            'other'
        )
    """)

    for table in _TABLES:
        op.execute(f"""
            ALTER TABLE {table}
            ALTER COLUMN category TYPE report_file_category_enum_new
            USING (
                CASE WHEN category::text = 'bead_specificity_chart'
                     THEN 'bead_specificity_chart_page_1'
                     ELSE category::text
                END
            )::report_file_category_enum_new
        """)

    op.execute("DROP TYPE report_file_category_enum")
    op.execute("ALTER TYPE report_file_category_enum_new RENAME TO report_file_category_enum")


def downgrade() -> None:
    """Downgrade schema.

    Collapses both bead-specificity pages back into one category. Since the
    (entity_id, category) uniqueness constraint means a downgrade could
    otherwise collide a patient/donor's page 1 and page 2 rows into the same
    category, page 2 rows are dropped first (both DB row and, as a heads up
    for anyone running this manually, their file on disk isn't cleaned up
    here and should be removed separately).
    """
    for table in _TABLES:
        op.execute(f"""
            DELETE FROM {table}
            WHERE category::text = 'bead_specificity_chart_page_2'
        """)

    op.execute("""
        CREATE TYPE report_file_category_enum_old AS ENUM (
            'hla_typing_report', 'crossmatch_report', 'bead_specificity_chart', 'other'
        )
    """)

    for table in _TABLES:
        op.execute(f"""
            ALTER TABLE {table}
            ALTER COLUMN category TYPE report_file_category_enum_old
            USING (
                CASE WHEN category::text = 'bead_specificity_chart_page_1'
                     THEN 'bead_specificity_chart'
                     ELSE category::text
                END
            )::report_file_category_enum_old
        """)

    op.execute("DROP TYPE report_file_category_enum")
    op.execute("ALTER TYPE report_file_category_enum_old RENAME TO report_file_category_enum")

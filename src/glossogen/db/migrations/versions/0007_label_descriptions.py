"""Add the label_descriptions table.

Revision ID: 0007_label_descriptions
Revises: 0006_dashboards
Create Date: 2026-08-25

A label is a plain string a run carries; nothing about the string says what the
cohort behind it was for, and researchers forget. This table is a group's glossary:
what each label means, keyed on the exact label string.

``(group_id, label)`` is the primary key rather than a surrogate id plus a unique
index, because a label's description is addressed by the label itself everywhere it
is read or written, and a label has at most one meaning per group.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false, reportMissingImports=false, reportUnknownVariableType=false

from alembic import op

revision = "0007_label_descriptions"
down_revision = "0006_dashboards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE label_descriptions (
            group_id    UUID  NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            label       TEXT  NOT NULL,
            description TEXT  NOT NULL,
            PRIMARY KEY (group_id, label)
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS label_descriptions")

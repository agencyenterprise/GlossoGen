"""Add the dashboards table.

Revision ID: 0006_dashboards
Revises: 0005_rename_external_org_id
Create Date: 2026-08-19

A dashboard is a saved analysis: which runs, which filters, and the charts drawn
over them. It belongs to a group, and everyone in that group sees it, which is what
"shared with collaborators" means here.

The charts live in one ``spec`` JSONB column rather than in a table of their own.
Nothing queries across dashboards by chart, so normalising them would buy a join and
a migration every time a chart gains a field. The column is validated by Pydantic on
read, so a spec written by an older version fails loudly at that dashboard rather
than corrupting a listing.

The name is unique per group: dashboards are referred to by name in conversation,
and two called "Noise sweep" in one group is a question nobody can answer.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false, reportMissingImports=false, reportUnknownVariableType=false

from alembic import op

revision = "0006_dashboards"
down_revision = "0005_rename_external_org_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE dashboards (
            id          UUID         PRIMARY KEY,
            group_id    UUID         NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            name        TEXT         NOT NULL,
            description TEXT         NOT NULL DEFAULT '',
            spec        JSONB        NOT NULL,
            created_by  TEXT         NOT NULL,
            created_at  TIMESTAMPTZ  NOT NULL,
            updated_at  TIMESTAMPTZ  NOT NULL
        )
        """)
    op.execute("CREATE UNIQUE INDEX dashboards_group_name_idx ON dashboards (group_id, name)")
    op.execute(
        "CREATE INDEX dashboards_group_updated_idx ON dashboards (group_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboards")

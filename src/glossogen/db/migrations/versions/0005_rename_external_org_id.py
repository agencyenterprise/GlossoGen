"""Rename ``groups.clerk_org_id`` to ``groups.external_org_id``.

Revision ID: 0005_rename_external_org_id
Revises: 0004_add_evaluation_content_hash
Create Date: 2026-08-18

The column holds the identifier a group carries in whichever external identity
provider a deployment configures. Naming it after one provider made the schema
describe a deployment choice rather than the platform.

``0001`` declares the column ``TEXT UNIQUE``, so Postgres created the constraint
``groups_clerk_org_id_key``. ``RENAME COLUMN`` renames neither that constraint nor
the index, so all three are renamed here.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false, reportMissingImports=false, reportUnknownVariableType=false

from alembic import op

revision = "0005_rename_external_org_id"
down_revision = "0004_add_evaluation_content_hash"
branch_labels = None
depends_on = None

# `ALTER TABLE ... RENAME CONSTRAINT` has no `IF EXISTS`, and this migration runs
# before the container serves a request. A database whose constraint was named
# something else should not fail the boot, so the rename is guarded.
_RENAME_CONSTRAINT = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{old}') THEN
            ALTER TABLE groups RENAME CONSTRAINT {old} TO {new};
        END IF;
    END
    $$
    """


def upgrade() -> None:
    op.execute("ALTER TABLE groups RENAME COLUMN clerk_org_id TO external_org_id")
    op.execute("ALTER INDEX IF EXISTS idx_groups_clerk_org_id RENAME TO idx_groups_external_org_id")
    op.execute(
        _RENAME_CONSTRAINT.format(
            old="groups_clerk_org_id_key",
            new="groups_external_org_id_key",
        )
    )


def downgrade() -> None:
    op.execute(
        _RENAME_CONSTRAINT.format(
            old="groups_external_org_id_key",
            new="groups_clerk_org_id_key",
        )
    )
    op.execute("ALTER INDEX IF EXISTS idx_groups_external_org_id RENAME TO idx_groups_clerk_org_id")
    op.execute("ALTER TABLE groups RENAME COLUMN external_org_id TO clerk_org_id")

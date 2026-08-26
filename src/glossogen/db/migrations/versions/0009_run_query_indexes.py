"""Index the runs table for the queries the platform actually runs.

Revision ID: 0009_run_query_indexes
Revises: 0008_add_run_labels
Create Date: 2026-08-26

Every runs listing orders by the unix-epoch prefix of ``run_dir_name`` (when the
simulation originally ran), not by ``created_at`` (when the row was inserted,
which an import changes). The old ``idx_runs_group_created_at`` indexed a sort no
query performs while the sort every listing performs had no index; these two
expression indexes replace it, one per branch of ``list_runs_for_group``.

The partial index serves ``list_children_of_run`` and narrows
``list_derived_source_counts``: both address runs by their recorded timeline
parent, and only derived runs carry one.

``idx_groups_external_org_id`` duplicated the column's UNIQUE constraint index
since 0001 and is dropped.

Left unindexed on purpose: the OAuth tables' purge and revocation scans (tiny,
boot-purged tables where an index would cost a write per token issued), and the
backfill's ``labels IS NULL`` scan (transitional; it matches nothing once the
first boot after 0008 has run).
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false, reportMissingImports=false, reportUnknownVariableType=false

from alembic import op

revision = "0009_run_query_indexes"
down_revision = "0008_add_run_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX idx_runs_group_epoch ON runs (
            group_id,
            (split_part(run_dir_name, '_', 1)::bigint) DESC,
            run_dir_name DESC
        )
        """)
    op.execute("""
        CREATE INDEX idx_runs_group_scenario_epoch ON runs (
            group_id,
            scenario,
            (split_part(run_dir_name, '_', 1)::bigint) DESC,
            run_dir_name DESC
        )
        """)
    op.execute("""
        CREATE INDEX idx_runs_group_source ON runs (
            group_id, source_run_scenario, source_run_dir_name
        )
        WHERE source_run_scenario IS NOT NULL
        """)
    op.execute("DROP INDEX IF EXISTS idx_runs_group_created_at")
    op.execute("DROP INDEX IF EXISTS idx_groups_external_org_id")


def downgrade() -> None:
    op.execute("CREATE INDEX idx_runs_group_created_at ON runs (group_id, created_at DESC)")
    op.execute("CREATE INDEX idx_groups_external_org_id ON groups (external_org_id)")
    op.execute("DROP INDEX IF EXISTS idx_runs_group_epoch")
    op.execute("DROP INDEX IF EXISTS idx_runs_group_scenario_epoch")
    op.execute("DROP INDEX IF EXISTS idx_runs_group_source")

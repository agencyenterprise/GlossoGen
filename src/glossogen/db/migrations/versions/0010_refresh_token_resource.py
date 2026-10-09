"""Preserve the OAuth resource indicator across token refreshes.

Revision ID: 0010_refresh_token_resource
Revises: 0009_run_query_indexes
Create Date: 2026-10-09
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false

from alembic import op

revision = "0010_refresh_token_resource"
down_revision = "0009_run_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN resource TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN resource")

"""Add evaluation_content_hash column to the runs table.

Revision ID: 0004_add_evaluation_content_hash
Revises: 0003_pending_oauth_consent
Create Date: 2026-07-03

Caches a stable 32-char hex digest of the run's ``<scenario>_report.json``
measurements list (see ``compute_measurements_hash``). The
``schmidt sync-metadata-to-prod`` tool consults this column via
``RunSummary`` on the paginated runs list to detect real eval drift; before
this migration it had to PUT every eval report unconditionally on every
sync because prod exposed no cheap drift signal.

Nullable — existing rows stay ``NULL`` until the next ``PUT /evaluation``
handler run (or the one-shot backfill script) populates them.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false, reportMissingImports=false, reportUnknownVariableType=false

from alembic import op

revision = "0004_add_evaluation_content_hash"
down_revision = "0003_pending_oauth_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE runs ADD COLUMN evaluation_content_hash TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS evaluation_content_hash")

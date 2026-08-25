"""Add the labels mirror column to runs.

Revision ID: 0008_add_run_labels
Revises: 0007_label_descriptions
Create Date: 2026-08-25

Labels stay authoritative on disk, in each run directory's ``labels.json``, so a
run folder keeps carrying its labels wherever it is copied. This column is the
server's mirror of that file: the label union and label filtering read it instead
of opening one file per run.

``NULL`` means the row has not been mirrored yet, and readers fall back to the
file; ``'[]'`` means the file was read and holds no labels. The server backfills
``NULL`` rows at startup and repairs drift whenever it reads a run's file anyway.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false, reportMissingImports=false, reportUnknownVariableType=false

from alembic import op

revision = "0008_add_run_labels"
down_revision = "0007_label_descriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE runs ADD COLUMN labels JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS labels")

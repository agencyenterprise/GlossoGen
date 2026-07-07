"""Create groups, runs, and user_last_active_group tables.

Revision ID: 0001_groups_and_runs
Revises:
Create Date: 2026-05-23

Multi-tenancy foundation: ``groups`` is authoritative for tenancy (its rows
outlive Clerk orgs so foreign keys never dangle); ``runs`` indexes the
filesystem ``runs/{scenario}/{run_dir_name}/`` directories with group ownership;
``user_last_active_group`` powers the root-redirect to a user's last group.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false

from alembic import op

revision = "0001_groups_and_runs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp"
        """)
    op.execute("""
        CREATE TABLE groups (
            id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
            clerk_org_id  TEXT         UNIQUE,
            slug          TEXT         NOT NULL UNIQUE,
            name          TEXT         NOT NULL,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """)
    op.execute("""
        CREATE INDEX idx_groups_clerk_org_id ON groups (clerk_org_id)
        """)
    op.execute("""
        CREATE TABLE runs (
            id                      BIGSERIAL    PRIMARY KEY,
            group_id                UUID         NOT NULL REFERENCES groups(id) ON DELETE RESTRICT,
            scenario                TEXT         NOT NULL,
            run_dir_name            TEXT         NOT NULL,
            status                  TEXT         NOT NULL,
            created_at              TIMESTAMPTZ  NOT NULL,
            created_by_user_id      TEXT,
            source_run_scenario     TEXT,
            source_run_dir_name     TEXT,
            UNIQUE (scenario, run_dir_name)
        )
        """)
    op.execute("""
        CREATE INDEX idx_runs_group_created_at ON runs (group_id, created_at DESC)
        """)
    op.execute("""
        CREATE TABLE user_last_active_group (
            user_id     TEXT         PRIMARY KEY,
            group_id    UUID         NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_last_active_group")
    op.execute("DROP TABLE IF EXISTS runs")
    op.execute("DROP TABLE IF EXISTS groups")

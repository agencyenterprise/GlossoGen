"""Migrate OAuth state from SQLite into Postgres and add group scoping.

Revision ID: 0002_oauth_tables
Revises: 0001_groups_and_runs
Create Date: 2026-05-23

The MCP server's OAuth state used to live in a per-volume SQLite file. Moving
it into Postgres makes the deployment story consistent (single source of
truth, survives multi-instance deploys) and lets every issued
authorization code, access token, and refresh token carry the ``group_id``
the user picked at the consent step.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false

from alembic import op

revision = "0002_oauth_tables"
down_revision = "0001_groups_and_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE oauth_clients (
            client_id          TEXT  PRIMARY KEY,
            client_secret      TEXT,
            metadata_json      TEXT  NOT NULL,
            issued_at          BIGINT,
            secret_expires_at  BIGINT
        )
        """)
    op.execute("""
        CREATE TABLE authorization_codes (
            code                              TEXT         PRIMARY KEY,
            client_id                         TEXT         NOT NULL,
            group_id                          UUID         NOT NULL
                REFERENCES groups(id) ON DELETE CASCADE,
            scopes                            TEXT         NOT NULL,
            code_challenge                    TEXT         NOT NULL,
            redirect_uri                      TEXT         NOT NULL,
            redirect_uri_provided_explicitly  BOOLEAN      NOT NULL,
            resource                          TEXT,
            expires_at                        TIMESTAMPTZ  NOT NULL
        )
        """)
    op.execute("""
        CREATE TABLE access_tokens (
            token       TEXT         PRIMARY KEY,
            client_id   TEXT         NOT NULL,
            group_id    UUID         NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            scopes      TEXT         NOT NULL,
            resource    TEXT,
            expires_at  TIMESTAMPTZ
        )
        """)
    op.execute("""
        CREATE TABLE refresh_tokens (
            token       TEXT         PRIMARY KEY,
            client_id   TEXT         NOT NULL,
            group_id    UUID         NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            scopes      TEXT         NOT NULL,
            expires_at  TIMESTAMPTZ
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refresh_tokens")
    op.execute("DROP TABLE IF EXISTS access_tokens")
    op.execute("DROP TABLE IF EXISTS authorization_codes")
    op.execute("DROP TABLE IF EXISTS oauth_clients")

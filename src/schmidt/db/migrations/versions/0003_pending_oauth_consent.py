"""Track pending OAuth consent requests for Clerk-gated approval.

Revision ID: 0003_pending_oauth_consent
Revises: 0002_oauth_tables
Create Date: 2026-05-26

In Clerk mode the OAuth ``authorize`` endpoint cannot synchronously create
an authorization code — the user must first sign in via Clerk on the
frontend and pick which group they want to authorize. The backend stores
the original ``AuthorizationParams`` keyed by a random ``request_id`` and
redirects the browser to the frontend consent page; the frontend POSTs
back with the chosen ``group_slug`` once the user is authenticated, the
backend then materializes the authorization code with that ``group_id``.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false, reportMissingImports=false, reportUnknownVariableType=false

from alembic import op

revision = "0003_pending_oauth_consent"
down_revision = "0002_oauth_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pending_oauth_consents (
            request_id                        TEXT         PRIMARY KEY,
            client_id                         TEXT         NOT NULL,
            scopes                            TEXT         NOT NULL,
            code_challenge                    TEXT         NOT NULL,
            redirect_uri                      TEXT         NOT NULL,
            redirect_uri_provided_explicitly  BOOLEAN      NOT NULL,
            resource                          TEXT,
            state                             TEXT,
            expires_at                        TIMESTAMPTZ  NOT NULL
        )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pending_oauth_consents")

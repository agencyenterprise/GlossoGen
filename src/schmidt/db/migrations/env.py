"""Alembic environment for schmidt.

Alembic uses SQLAlchemy for connection management here — that's confined to
this file. Migration bodies must remain raw SQL via ``op.execute(...)``; no
Table/Column declarations belong in any ``versions/`` file.
"""

# pyright: reportPrivateImportUsage=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false

import os

from alembic import context
from sqlalchemy import create_engine


def _resolve_database_url() -> str:
    """Read ``DATABASE_URL`` from env and pin SQLAlchemy to the psycopg3 driver.

    psycopg2 is not installed; rewriting the URL scheme is the standard way to
    tell SQLAlchemy to dispatch to ``psycopg`` (v3) instead of the default
    ``psycopg2`` dialect.
    """
    url = os.environ.get("DATABASE_URL")
    if url is None:
        raise RuntimeError(
            "DATABASE_URL is not set. Alembic needs it to connect for upgrade/downgrade."
        )
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to the database."""
    context.configure(
        url=_resolve_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database."""
    engine = create_engine(_resolve_database_url(), future=True)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

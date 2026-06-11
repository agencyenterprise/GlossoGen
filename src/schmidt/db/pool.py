"""Async Postgres connection pool wrapper.

The pool is created once per process at FastAPI lifespan startup and reused
across all requests. All query code in the project uses ``psycopg.AsyncConnection``
acquired from this pool; SQLAlchemy is intentionally not used.
"""

import logging
import os

from psycopg import AsyncConnection
from psycopg.rows import TupleRow
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

DbPool = AsyncConnectionPool[AsyncConnection[TupleRow]]


def get_database_url() -> str | None:
    """Return the Postgres connection string from the ``DATABASE_URL`` env var.

    Returns ``None`` when the variable is unset or blank, which selects
    no-database local mode: the runs index is derived from the filesystem and
    OAuth state is held in memory. Prod sets ``DATABASE_URL`` to a Postgres
    connection string.
    """
    url = os.environ.get("DATABASE_URL")
    if url is None or url.strip() == "":
        return None
    return url


async def create_pool(database_url: str | None, min_size: int, max_size: int) -> DbPool | None:
    """Open and warm a psycopg3 async connection pool, or ``None`` in no-DB mode.

    Returns ``None`` when ``database_url`` is ``None`` so the caller runs in
    no-database local mode.
    """
    if database_url is None:
        return None
    pool: DbPool = AsyncConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        open=False,
    )
    await pool.open()
    await pool.wait()
    logger.info("Postgres pool ready (min=%d max=%d)", min_size, max_size)
    return pool


async def close_pool(pool: DbPool | None) -> None:
    """Close the connection pool during FastAPI lifespan shutdown."""
    if pool is None:
        return
    await pool.close()
    logger.info("Postgres pool closed")

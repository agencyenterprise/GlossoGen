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


def get_database_url() -> str:
    """Return the Postgres connection string from the ``DATABASE_URL`` env var.

    Raises a ``RuntimeError`` if the variable is not set, since the server
    cannot function without a database.
    """
    url = os.environ.get("DATABASE_URL")
    if url is None:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it to a Postgres connection string "
            "(e.g. postgresql://user:pass@host:5432/dbname)."
        )
    return url


async def create_pool(database_url: str, min_size: int, max_size: int) -> DbPool:
    """Open and warm a psycopg3 async connection pool for the given URL."""
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


async def close_pool(pool: DbPool) -> None:
    """Close the connection pool during FastAPI lifespan shutdown."""
    await pool.close()
    logger.info("Postgres pool closed")

"""A stand-in for the Postgres pool, for code whose queries a test replaces.

The pool only hands out connections; each test monkeypatches the query
functions the module under test imported, so the connection is never read.
``connections_taken`` lets a test assert that a path took no connection at all.
"""

from typing import cast

from glossogen.db.pool import DbPool


class StubConnection:
    """Async context manager yielding a connection nothing looks at."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


class CountingPool:
    """Hands out stub connections and counts how many were taken."""

    def __init__(self) -> None:
        self.connections_taken = 0

    def connection(self) -> StubConnection:
        """Return a stub connection and count it."""
        self.connections_taken += 1
        return StubConnection()

    def as_db_pool(self) -> DbPool:
        """This pool, typed as the pool the server code is given."""
        return cast(DbPool, self)

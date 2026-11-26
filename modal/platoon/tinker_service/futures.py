"""The futures of the Tinker API: a request that takes time answers with a request id at once, and
the client polls ``retrieve_future`` for its result.

A future fails with the error category ``user`` for a ``ValueError``, a request the service refuses,
and ``server`` for any other exception. A delivered result stays retrievable for ``KEEP_SECONDS``,
in case the client asks again after a dropped connection.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Coroutine
from enum import StrEnum
from typing import Any, NamedTuple

from pydantic import BaseModel

logger = logging.getLogger(__name__)

KEEP_SECONDS = 600.0


class FutureStatus(StrEnum):
    """Where a future stands."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class ErrorCategory(StrEnum):
    """The Tinker API's error categories: the request was refused, or the service failed."""

    USER = "user"
    SERVER = "server"


class FutureState(NamedTuple):
    """A future's status, and its result or its error."""

    status: FutureStatus
    result: BaseModel | None
    error: str | None
    category: ErrorCategory | None


PENDING = FutureState(status=FutureStatus.PENDING, result=None, error=None, category=None)


class FutureStore:
    """The futures of one service, by request id."""

    def __init__(self) -> None:
        self.tasks: dict[str, asyncio.Task[BaseModel]] = {}
        self.delivered_at: dict[str, float] = {}

    def submit(self, *, work: Coroutine[Any, Any, BaseModel]) -> str:
        """Start ``work`` and return its request id."""
        request_id = f"req-{uuid.uuid4().hex}"
        self.tasks[request_id] = asyncio.create_task(work)
        return request_id

    async def retrieve(self, *, request_id: str, wait_seconds: float) -> FutureState | None:
        """The future's state, waiting up to ``wait_seconds`` for it to settle; None for an unknown
        id."""
        self.forget_old_results()
        task = self.tasks.get(request_id)
        if task is None:
            return None
        done, _ = await asyncio.wait({task}, timeout=wait_seconds)
        if not done:
            return PENDING
        self.delivered_at.setdefault(request_id, time.monotonic())
        return settled_state(task=task)

    def forget_old_results(self) -> None:
        """Drop the results delivered more than ``KEEP_SECONDS`` ago."""
        now = time.monotonic()
        for request_id, delivered in list(self.delivered_at.items()):
            if now - delivered > KEEP_SECONDS:
                del self.delivered_at[request_id]
                del self.tasks[request_id]


def settled_state(*, task: asyncio.Task[BaseModel]) -> FutureState:
    """The state of a task that has settled: its result, or its error with the error's category."""
    error = task.exception()
    if error is None:
        return FutureState(
            status=FutureStatus.DONE, result=task.result(), error=None, category=None
        )
    logger.error("request failed", exc_info=error)
    category = ErrorCategory.SERVER
    if isinstance(error, ValueError):
        category = ErrorCategory.USER
    return FutureState(
        status=FutureStatus.FAILED, result=None, error=repr(error), category=category
    )

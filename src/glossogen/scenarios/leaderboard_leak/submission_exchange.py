"""Holds each submitting agent's ``submit_answer`` call until its task's log is ready.

Every submission waits on a future keyed by round, task and agent. The scenario
resolves all of a task's futures at once: when the fourth submission arrives, or
when the round ends with the task still open, or when the session stops. A waiting
call makes no model request, so the wait costs wall-clock time and no tokens.
"""

import asyncio
from collections.abc import Mapping
from typing import NamedTuple


class _TaskKey(NamedTuple):
    round_number: int
    task: int


class SubmissionExchange:
    """The futures of every ``submit_answer`` call still waiting for its log."""

    def __init__(self) -> None:
        self._waiting: dict[_TaskKey, dict[str, asyncio.Future[str]]] = {}

    def wait_for_log(self, round_number: int, task: int, agent_id: str) -> asyncio.Future[str]:
        """The future ``agent_id``'s call awaits for ``task``'s log."""
        key = _TaskKey(round_number=round_number, task=task)
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._waiting.setdefault(key, {})[agent_id] = future
        return future

    def release(self, round_number: int, task: int, logs: Mapping[str, str]) -> None:
        """Answer every call waiting on ``task``, each with its agent's entry in ``logs``."""
        key = _TaskKey(round_number=round_number, task=task)
        for agent_id, future in self._waiting.pop(key, {}).items():
            if not future.done():
                future.set_result(logs[agent_id])

    def release_everything(self, text: str) -> None:
        """Answer every waiting call with ``text``, for a session that is stopping."""
        waiting = self._waiting
        self._waiting = {}
        for futures in waiting.values():
            for future in futures.values():
                if not future.done():
                    future.set_result(text)

    def waiting_task(self, round_number: int, agent_id: str) -> int | None:
        """The task ``agent_id``'s call is waiting on in ``round_number``, or None."""
        for key, futures in self._waiting.items():
            if key.round_number != round_number:
                continue
            future = futures.get(agent_id)
            if future is not None and not future.done():
                return key.task
        return None

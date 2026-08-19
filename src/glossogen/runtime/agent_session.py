"""Per-agent session state tracked by the simulation runtime.

Each agent connected to the runtime gets an ``AgentSession`` that holds its
notification queue, idle-tracking flag, per-channel read position, and
termination state.
"""

import asyncio
import contextlib
import itertools
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from glossogen.runtime.activity_notification import ActivityNotification, DoneNotification

logger = logging.getLogger(__name__)


class AgentSession:
    """Mutable session state for a single agent within the simulation runtime."""

    def __init__(
        self,
        agent_id: str,
    ) -> None:
        self.agent_id = agent_id
        self._queue: asyncio.Queue[ActivityNotification] = asyncio.Queue()
        self._last_seen_counts: dict[str, int] = {}
        self.is_idle = False
        self._active_calls: dict[int, float] = {}
        self._active_call_seq = itertools.count()
        self.read_notifications_in_flight = False
        self.last_non_blocking_dispatch_ts: float | None = None
        self._terminated = False
        self._done_reason = ""
        self._runner_finished = False

    @property
    def active_non_blocking_calls(self) -> int:
        """Number of non-blocking tool calls currently in flight for this agent."""
        return len(self._active_calls)

    def oldest_active_call_age(self, now: float) -> float | None:
        """Seconds the longest-running in-flight non-blocking call has been active.

        Returns ``None`` when no non-blocking call is in flight. Used by
        ``read_notifications`` to detect a zombie call (one stalled far longer
        than any legitimate tool body) so the agent is never starved of its
        notification queue by a tool that never returns.
        """
        if not self._active_calls:
            return None
        return now - min(self._active_calls.values())

    @property
    def runner_finished(self) -> bool:
        """True once this agent's runner has returned and will take no more turns.

        ``is_idle`` only becomes True inside ``wait_for_notification``, so an agent
        that stopped between notifications leaves it False forever. That happens on
        the ordinary path: a runner that reaches its ``max_turns`` cap returns
        without waiting again. What the clock needs to know is whether an agent will
        speak again in this phase, and a returned runner settles that, so it is
        tracked separately from the flag that only a waiting agent can set.
        """
        return self._runner_finished

    def mark_runner_finished(self, task: asyncio.Task[Any]) -> None:
        """Record that this agent's runner has returned.

        Shaped as a done callback so it can be handed straight to
        ``add_done_callback`` on the runner's task, which is the one place that
        knows about every way a runner can stop. It fires whether the runner
        returned, raised, or was cancelled, and all three mean the same thing to
        the clock: no further turns. ``task`` is the callback contract and is not
        read; the outcome does not change the answer.

        Bound to the session rather than looking one up by agent id, because a
        mid-run swap replaces the session while the outgoing runner is still
        settling. A callback that resolved the id later would mark the incoming
        session finished and strand the agent that had only just started.
        """
        del task
        self._runner_finished = True

    @property
    def terminated(self) -> bool:
        """True after a ``DoneNotification`` has been queued.

        Used to reject incoming tool calls from agents being swapped out
        so they cannot mutate simulation state mid-drain.
        """
        return self._terminated

    @contextlib.asynccontextmanager
    async def track_active_call(self) -> AsyncGenerator[None]:
        """Mark the agent busy for the duration of a non-blocking tool call.

        Use this around every tool body except ``read_notifications`` so
        the game clock cannot mistake an in-flight ``send_message`` /
        ``read_channel`` / scenario tool for genuine idleness when it
        runs in parallel with a ``read_notifications`` call. Also stamps
        ``last_non_blocking_dispatch_ts`` so ``read_notifications`` can
        detect sibling dispatches that already finished by the time the
        parallelism check runs.
        """
        call_id = next(self._active_call_seq)
        now = time.monotonic()
        self.last_non_blocking_dispatch_ts = now
        self._active_calls[call_id] = now
        try:
            yield
        finally:
            self._active_calls.pop(call_id, None)

    def record_channel_read(self, channel_id: str, message_count: int) -> None:
        """Record that this agent has seen all messages up to the given count."""
        self._last_seen_counts[channel_id] = message_count

    def set_last_seen_count(self, channel_id: str, count: int) -> None:
        """Set the read position for a channel.

        Used during resume to mark all pre-loaded messages as already seen,
        preventing the agent from receiving spurious new-message notifications.
        """
        self._last_seen_counts[channel_id] = count

    def get_last_seen_count(self, channel_id: str) -> int:
        """Return the message count at the time of the agent's last read_channel call.

        Returns 0 if the agent has never read this channel.
        """
        return self._last_seen_counts.get(channel_id, 0)

    def has_pending_notifications(self) -> bool:
        """Return True if there are unprocessed notifications in the queue."""
        return not self._queue.empty()

    def pending_notifications_count(self) -> int:
        """Return the number of notifications still queued for the agent."""
        return self._queue.qsize()

    def push_notification(self, notification: ActivityNotification) -> None:
        """Enqueue a notification for this agent. Non-blocking."""
        if isinstance(notification, DoneNotification):
            self._terminated = True
            self._done_reason = notification.reason
            logger.info("Agent %s marked terminated: %s", self.agent_id, notification.reason)
        else:
            logger.debug(
                "Agent %s queued notification type=%s",
                self.agent_id,
                notification.type.value,
            )
        self.is_idle = False
        self._queue.put_nowait(notification)

    async def wait_for_notification(self) -> ActivityNotification:
        """Block until a notification is available, then return it.

        If the session has already been terminated (a ``DoneNotification``
        was previously consumed), returns a ``DoneNotification`` immediately
        without blocking.
        """
        if self._terminated and self._queue.empty():
            logger.debug("Agent %s already terminated, returning done immediately", self.agent_id)
            return DoneNotification(reason=self._done_reason)
        if self._queue.empty():
            self.is_idle = True
            logger.debug("Agent %s is now idle, waiting for notification", self.agent_id)
        notification = await self._queue.get()
        self.is_idle = False
        logger.debug(
            "Agent %s woke up with notification type=%s", self.agent_id, notification.type.value
        )
        return notification

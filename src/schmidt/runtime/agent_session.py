"""Per-agent session state tracked by the simulation runtime.

Each agent connected to the runtime gets an ``AgentSession`` that holds its
notification queue, idle-tracking flag, per-channel read position, and
termination state.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncGenerator

from schmidt.runtime.activity_notification import ActivityNotification, DoneNotification

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
        self.active_non_blocking_calls = 0
        self.read_notifications_in_flight = False
        self.last_non_blocking_dispatch_ts: float | None = None
        self._terminated = False
        self._done_reason = ""

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
        self.active_non_blocking_calls += 1
        self.last_non_blocking_dispatch_ts = time.monotonic()
        try:
            yield
        finally:
            self.active_non_blocking_calls -= 1

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

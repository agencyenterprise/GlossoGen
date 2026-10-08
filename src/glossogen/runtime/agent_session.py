"""Per-agent session state tracked by the simulation runtime.

Each agent connected to the runtime gets an ``AgentSession`` that holds its
notification queue, per-channel read position, in-flight tool calls, and
termination state.
"""

import asyncio
import contextlib
import itertools
import logging
from collections import deque
from collections.abc import AsyncGenerator, Callable
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
        self._queue: deque[ActivityNotification] = deque()
        self._notification_listener: Callable[[], None] | None = None
        self._last_seen_counts: dict[str, int] = {}
        self._active_calls: set[int] = set()
        self._active_call_seq = itertools.count()
        self._terminated = False
        self._done_reason = ""
        self._runner_finished = False

    @property
    def active_non_blocking_calls(self) -> int:
        """Number of non-blocking tool calls currently in flight for this agent."""
        return len(self._active_calls)

    @property
    def runner_finished(self) -> bool:
        """True once this agent's runner has returned and will take no more turns.

        An agent counts as idle only while it is parked in ``read_notifications``,
        so an agent that stopped between notifications would never count as idle.
        That happens on the ordinary path: a runner that reaches its ``max_turns``
        cap returns without waiting again. What the clock needs to know is whether
        an agent will speak again in this phase, and a returned runner settles
        that, so it is tracked separately from the wait.
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

    @property
    def done_reason(self) -> str:
        """The reason carried by the ``DoneNotification`` that terminated this session."""
        return self._done_reason

    @contextlib.asynccontextmanager
    async def track_active_call(self) -> AsyncGenerator[None]:
        """Mark the agent busy for the duration of a tool call other than ``read_notifications``.

        The game clock refuses to end a phase while any agent has a call in
        flight, so a ``send_message`` or scenario tool still executing is never
        mistaken for an agent that has stopped.
        """
        call_id = next(self._active_call_seq)
        self._active_calls.add(call_id)
        try:
            yield
        finally:
            self._active_calls.discard(call_id)

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

    def pending_notifications_count(self) -> int:
        """Return the number of notifications still queued for the agent."""
        return len(self._queue)

    def pending_notifications(self) -> list[ActivityNotification]:
        """Return the queued notifications, oldest first, without removing them."""
        return list(self._queue)

    def take_next_notification(self) -> ActivityNotification | None:
        """Remove and return the oldest queued notification, or None when the queue is empty."""
        if not self._queue:
            return None
        return self._queue.popleft()

    def take_notifications(
        self, take: Callable[[ActivityNotification], bool]
    ) -> list[ActivityNotification]:
        """Remove and return, oldest first, every queued notification for which ``take`` is True."""
        taken = [notification for notification in self._queue if take(notification)]
        kept = [notification for notification in self._queue if not take(notification)]
        self._queue.clear()
        self._queue.extend(kept)
        return taken

    def discard_notifications(self, discard: Callable[[ActivityNotification], bool]) -> None:
        """Drop every queued notification for which ``discard`` returns True."""
        kept = [notification for notification in self._queue if not discard(notification)]
        self._queue.clear()
        self._queue.extend(kept)

    def set_notification_listener(self, listener: Callable[[], None] | None) -> None:
        """Install, or clear with None, a callback run after every queued notification.

        The wait registry installs one while the agent is parked, so a
        notification that satisfies the wait resumes it.
        """
        self._notification_listener = listener

    def push_notification(self, notification: ActivityNotification) -> None:
        """Enqueue a notification for this agent and tell the wait registry. Non-blocking."""
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
        self._queue.append(notification)
        if self._notification_listener is not None:
            self._notification_listener()

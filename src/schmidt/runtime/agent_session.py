"""Per-agent session state tracked by the simulation runtime.

Each agent connected to the runtime gets an ``AgentSession`` that holds its
notification queue, reaction delay configuration, idle-tracking flag, and
termination state.
"""

import asyncio
import logging
import random

from schmidt.runtime.activity_notification import ActivityNotification, DoneNotification

logger = logging.getLogger(__name__)


class AgentSession:
    """Mutable session state for a single agent within the simulation runtime."""

    def __init__(
        self,
        agent_id: str,
        reaction_delay_min: float,
        reaction_delay_max: float,
    ) -> None:
        self.agent_id = agent_id
        self.reaction_delay_min = reaction_delay_min
        self.reaction_delay_max = reaction_delay_max
        self._queue: asyncio.Queue[ActivityNotification] = asyncio.Queue()
        self.is_idle = False
        self._terminated = False
        self._done_reason = ""

    def sample_reaction_delay(self) -> float:
        """Return a random delay in seconds drawn from the agent's configured range."""
        return random.uniform(self.reaction_delay_min, self.reaction_delay_max)

    def has_pending_notifications(self) -> bool:
        """Return True if there are unprocessed notifications in the queue."""
        return not self._queue.empty()

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
        self.is_idle = True
        if self._terminated and self._queue.empty():
            logger.debug("Agent %s already terminated, returning done immediately", self.agent_id)
            return DoneNotification(reason=self._done_reason)
        logger.debug("Agent %s is now idle, waiting for notification", self.agent_id)
        notification = await self._queue.get()
        self.is_idle = False
        logger.debug(
            "Agent %s woke up with notification type=%s", self.agent_id, notification.type.value
        )
        return notification

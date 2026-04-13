"""Platform framework for living world simulations that run alongside agents.

Every scenario provides a ``ScenarioWorld`` that runs as its own asyncio task.
The world receives message events and round advance signals via a ``WorldContext``,
and can push notifications to agents via ``send_update``.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import NamedTuple

from schmidt.event_logger import EventLogger
from schmidt.models.event import WorldEventDelivered
from schmidt.runtime.activity_notification import NewInfoNotification
from schmidt.runtime.agent_session import AgentSession

logger = logging.getLogger(__name__)


class MessageEvent(NamedTuple):
    """Delivered to the world when an agent sends a message."""

    agent_id: str
    channel_id: str
    text: str
    token_count: int


class RoundAdvancedEvent(NamedTuple):
    """Delivered to the world when the game clock advances to a new round."""

    round_number: int


WorldEvent = MessageEvent | RoundAdvancedEvent


class WorldContext:
    """Provides world simulations with event streams and agent notification capabilities.

    Created by the supervisor before the simulation runtime, and passed to the
    world's ``run`` method as an asyncio task. The world awaits ``next_event``
    to receive agent messages and round transitions, and calls ``send_update``
    to broadcast notifications to all agents.
    """

    def __init__(
        self,
        agent_sessions: dict[str, AgentSession],
        event_logger: EventLogger,
    ) -> None:
        self._agent_sessions = agent_sessions
        self._event_logger = event_logger
        self._event_queue: asyncio.Queue[WorldEvent] = asyncio.Queue()

    async def next_event(self) -> WorldEvent:
        """Block until the next world event (message or round advance)."""
        return await self._event_queue.get()

    async def send_update(self, text: str) -> None:
        """Broadcast a world notification to all agent sessions.

        Pushes a ``NewInfoNotification`` to each agent and logs a
        ``WorldEventDelivered`` event per agent for replay and evaluation.
        """
        for agent_id, session in self._agent_sessions.items():
            session.push_notification(
                notification=NewInfoNotification(text=text),
            )
            await self._event_logger.log(
                event=WorldEventDelivered(
                    agent_id=agent_id,
                    round_number=self._event_logger.current_round,
                    text=text,
                )
            )
        logger.debug("World update broadcast to %d agents: %s", len(self._agent_sessions), text)

    def enqueue_message_event(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Enqueue a message event from an agent. Called synchronously by the runtime."""
        self._event_queue.put_nowait(
            MessageEvent(
                agent_id=agent_id,
                channel_id=channel_id,
                text=text,
                token_count=token_count,
            )
        )

    def signal_round_advanced(self, round_number: int) -> None:
        """Enqueue a round advance event. Called synchronously by the game clock."""
        self._event_queue.put_nowait(RoundAdvancedEvent(round_number=round_number))


class ScenarioWorld(ABC):
    """A living world simulation that runs alongside agents as its own asyncio task.

    Every scenario implements this to define dynamic world behavior: real-time
    state changes, environmental updates, and reactive events based on agent
    communication. The ``run`` method is started as an asyncio task by the
    supervisor and cancelled when the simulation ends.
    """

    @abstractmethod
    async def run(self, context: WorldContext) -> None:
        """Main world loop. Process events from ``context.next_event()`` and
        send updates via ``context.send_update()``. Handle ``CancelledError``
        for cleanup.
        """
        ...

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Called synchronously from ``send_message`` before the event is enqueued.

        Override this to update world state that must be visible immediately
        (e.g. token accumulation, patient death). The default is a no-op.
        Async notifications should be sent from the ``run`` loop instead.
        """
        _ = agent_id, channel_id, text, token_count

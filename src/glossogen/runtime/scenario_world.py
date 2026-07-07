"""Platform framework for living world simulations that run alongside agents.

Every scenario provides a ``ScenarioWorld`` that runs as its own asyncio task.
The world receives message events and round advance signals via a ``WorldContext``,
and can push channel-scoped notifications via ``send_update_to_channel``.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import NamedTuple

from glossogen.channel_router import ChannelRouter
from glossogen.event_logger import EventLogger
from glossogen.models.event import (
    ChannelHistoryCleared,
    ChannelMembershipChanged,
    WorldEventDelivered,
)
from glossogen.runtime.activity_notification import NewInfoNotification
from glossogen.runtime.agent_session import AgentSession

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

    channel_router: ChannelRouter
    get_current_round: Callable[[], int]

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

    async def send_update_to_channel(self, channel_id: str, text: str) -> None:
        """Push a world notification only to agents in the specified channel.

        Agents outside the channel do not receive the notification. One
        ``WorldEventDelivered`` event is logged per delivered agent.
        """
        router = self.channel_router
        member_ids = router.get_channel_member_ids(channel_id=channel_id)
        for agent_id in member_ids:
            session = self._agent_sessions.get(agent_id)
            if session is None:
                continue
            session.push_notification(
                notification=NewInfoNotification(text=text),
            )
            await self._event_logger.log(
                event=WorldEventDelivered(
                    agent_id=agent_id,
                    round_number=self.get_current_round(),
                    text=text,
                )
            )
        logger.debug(
            "World update delivered to channel %s (%d agents): %s",
            channel_id,
            len(member_ids),
            text,
        )

    async def send_update_to_agent(self, agent_id: str, text: str) -> None:
        """Push a world notification to a single agent.

        Mirrors ``send_update_to_channel`` but targets one session. One
        ``WorldEventDelivered`` event is logged for the delivered agent.
        """
        session = self._agent_sessions.get(agent_id)
        if session is None:
            return
        session.push_notification(notification=NewInfoNotification(text=text))
        await self._event_logger.log(
            event=WorldEventDelivered(
                agent_id=agent_id,
                round_number=self.get_current_round(),
                text=text,
            )
        )
        logger.debug(
            "World update delivered to agent %s: %s",
            agent_id,
            text,
        )

    async def update_channel_members(
        self,
        channel_id: str,
        member_agent_ids: list[str],
        reason: str,
    ) -> None:
        """Replace a channel's member list and log the change.

        Newly added members have their session ``last_seen_count`` for this
        channel set to the current message count so pre-join messages do
        not trigger ``send_message`` concurrency conflicts. Membership is
        rechecked on every ``send_message`` / ``read_channel`` call, so the
        change takes effect immediately for all subsequent tool invocations.
        """
        router = self.channel_router
        old_members = set(router.get_channel_member_ids(channel_id=channel_id))
        new_members = set(member_agent_ids)
        newly_added = new_members - old_members
        history_len = router.get_message_count(channel_id=channel_id)
        router.update_membership(
            channel_id=channel_id,
            member_agent_ids=member_agent_ids,
        )
        for agent_id in newly_added:
            session = self._agent_sessions.get(agent_id)
            if session is None:
                continue
            session.set_last_seen_count(
                channel_id=channel_id,
                count=history_len,
            )
        await self._event_logger.log(
            event=ChannelMembershipChanged(
                channel_id=channel_id,
                round_number=self.get_current_round(),
                member_agent_ids=list(member_agent_ids),
                reason=reason,
            )
        )

    async def clear_channel_history(self, channel_id: str, reason: str) -> None:
        """Wipe a channel's message history and reset per-agent read positions.

        Agents' ``last_seen_count`` for this channel is reset to zero so that
        messages appended after the wipe are correctly flagged as new.
        """
        router = self.channel_router
        router.clear_history(channel_id=channel_id)
        for session in self._agent_sessions.values():
            session.set_last_seen_count(channel_id=channel_id, count=0)
        await self._event_logger.log(
            event=ChannelHistoryCleared(
                channel_id=channel_id,
                round_number=self.get_current_round(),
                reason=reason,
            )
        )

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
        send updates via ``context.send_update_to_channel()``. Handle
        ``CancelledError`` for cleanup.
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

    def get_globally_disabled_channels(self) -> frozenset[str]:
        """Return channel IDs that have been globally disabled for the rest of the run.

        The runtime treats these channels as effectively dead for any
        agent swapped in via the in-run scheduler: the swap logic forces
        ``ChannelVisibilityNone`` on them (history hidden, predecessor
        tool calls dropped) and excludes them from the wake-up
        notification so the new agent does not get spurious "you have
        new messages" alerts on a channel they shouldn't be reading.
        Default returns the empty set; scenarios that disable channels
        mid-run (e.g. veyru's ``disable_postmortem_globally``) override.
        """
        return frozenset()

    def on_agent_swapped_mid_run(self, agent_id: str, round_number: int) -> None:
        """Notify the world that an in-run agent swap has fired.

        Called by the runtime's swap dispatcher right after a fresh
        agent has been instantiated for ``agent_id`` at the start of
        ``round_number``. Scenarios can use this to suppress
        injection content that would leak prior-round context the
        newly-swapped agent should not see (e.g. veyru's
        ``PREVIOUS VEYRU RESULT`` block, which describes a round the
        new agent did not participate in). Default is a no-op.
        """
        _ = agent_id, round_number

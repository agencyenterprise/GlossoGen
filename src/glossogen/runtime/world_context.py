"""The runtime's ``WorldContext``: world updates delivered to agent sessions and logged.

Created by the supervisor before the simulation runtime, which sets
``channel_router`` and ``get_current_round`` once it exists. The game clock
enqueues round advances through ``signal_round_advanced``.
"""

import asyncio
import logging
from collections.abc import Callable

from glossogen.models.event import (
    ChannelHistoryCleared,
    ChannelMembershipChanged,
    WorldEventDelivered,
)
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.channel_router import ChannelRouter
from glossogen.runtime.event_logger import EventLogger
from glossogen.scenario_contract.activity_notification import NewInfoNotification
from glossogen.scenario_contract.scenario_world import RoundAdvancedEvent, WorldContext

logger = logging.getLogger(__name__)


class RuntimeWorldContext(WorldContext):
    """Delivers a world's updates to agent sessions and logs them, and queues round advances."""

    channel_router: ChannelRouter
    get_current_round: Callable[[], int]

    def __init__(
        self,
        agent_sessions: dict[str, AgentSession],
        event_logger: EventLogger,
    ) -> None:
        self._agent_sessions = agent_sessions
        self._event_logger = event_logger
        self._event_queue: asyncio.Queue[RoundAdvancedEvent] = asyncio.Queue()

    async def next_event(self) -> RoundAdvancedEvent:
        """Block until the next round advance."""
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
                notification=NewInfoNotification(text=text, kind="world"),
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
        session.push_notification(notification=NewInfoNotification(text=text, kind="world"))
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

    def signal_round_advanced(self, round_number: int) -> None:
        """Enqueue a round advance event. Called synchronously by the game clock."""
        self._event_queue.put_nowait(RoundAdvancedEvent(round_number=round_number))

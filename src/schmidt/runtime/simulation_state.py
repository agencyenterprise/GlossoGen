"""Shared simulation state accessed by MCP tools and the game clock.

Holds channel state, per-agent notification queues, per-channel write locks,
and event logging. Does not define MCP tools — those live in ``mcp_tools``.
"""

import asyncio
import logging
from collections.abc import Callable

from schmidt.channel_router import ChannelRouter
from schmidt.event_logger import EventLogger
from schmidt.models.channel import Channel
from schmidt.runtime.activity_notification import DoneNotification
from schmidt.runtime.agent_session import AgentSession
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class SimulationRuntime:
    """Shared world state that MCP tools and the game clock interact with."""

    def __init__(
        self,
        scenario: SimulationScenario,
        channels: list[Channel],
        event_logger: EventLogger,
        agent_sessions: dict[str, AgentSession],
    ) -> None:
        self._scenario = scenario
        self._channel_router = ChannelRouter(channels=channels)
        self._event_logger = event_logger
        self._agent_sessions = agent_sessions
        self._channel_locks: dict[str, asyncio.Lock] = {
            ch.channel_id: asyncio.Lock() for ch in channels
        }
        self._on_message_callbacks: list[Callable[[], None]] = []

    @property
    def scenario(self) -> SimulationScenario:
        """Access the scenario for display name lookups."""
        return self._scenario

    @property
    def channel_router(self) -> ChannelRouter:
        """Access the underlying channel router."""
        return self._channel_router

    @property
    def event_logger(self) -> EventLogger:
        """Access the event logger for writing JSONL events."""
        return self._event_logger

    @property
    def agent_sessions(self) -> dict[str, AgentSession]:
        """Access per-agent sessions."""
        return self._agent_sessions

    def get_channel_lock(self, channel_id: str) -> asyncio.Lock:
        """Return the write lock for a channel."""
        return self._channel_locks[channel_id]

    def add_on_message_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked after every message is sent.

        Used by the game clock to reset the quiet-period timer.
        """
        self._on_message_callbacks.append(callback)

    def fire_on_message_callbacks(self) -> None:
        """Invoke all registered on-message callbacks."""
        for callback in self._on_message_callbacks:
            callback()

    def resolve_session(self, agent_id: str) -> AgentSession:
        """Look up the session for an agent, raising if unknown."""
        session = self._agent_sessions.get(agent_id)
        if session is None:
            raise ValueError(f"Unknown agent: {agent_id}")
        return session

    def broadcast_done(self, reason: str) -> None:
        """Push a done notification to all agents."""
        logger.info(
            "Broadcasting done to %d agents: %s",
            len(self._agent_sessions),
            reason,
        )
        for session in self._agent_sessions.values():
            session.push_notification(
                notification=DoneNotification(reason=reason),
            )

"""Shared simulation state accessed by MCP tools and the game clock.

Holds channel state, per-agent notification queues, per-channel write locks,
per-agent tool authorization allowlists, world context, and event logging.
Does not define MCP tools — those live in ``mcp_tools``.
"""

import asyncio
import logging
from collections.abc import Callable

from schmidt.channel_router import ChannelRouter
from schmidt.event_logger import EventLogger
from schmidt.llm.token_counter import TokenCounter, create_token_counter
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel
from schmidt.runtime.activity_notification import DoneNotification
from schmidt.runtime.agent_session import AgentSession
from schmidt.runtime.scenario_world import WorldContext
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
        agent_tool_allowlists: dict[str, frozenset[str]],
        world_context: WorldContext,
        agent_configs: list[AgentConfig],
    ) -> None:
        self._scenario = scenario
        self._channel_router = ChannelRouter(channels=channels)
        self._event_logger = event_logger
        self._agent_sessions = agent_sessions
        self._agent_tool_allowlists = agent_tool_allowlists
        self._world_context = world_context
        world_context._channel_router = self._channel_router
        self._agent_configs_by_id = {c.agent_id: c for c in agent_configs}
        self._token_counters: dict[str, TokenCounter] = {}
        self._channel_locks: dict[str, asyncio.Lock] = {
            ch.channel_id: asyncio.Lock() for ch in channels
        }
        self._on_message_callbacks: list[Callable[[], None]] = []
        self._channel_message_count_at_round_start: dict[int, dict[str, int]] = {}

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

    @property
    def channel_message_count_at_round_start(self) -> dict[int, dict[str, int]]:
        """Per-round per-channel message counts captured when each round began.

        Populated by ``snapshot_round_start`` on every round advance.
        Used by the in-run swap flow to compute per-channel
        ``member_join_index`` for ``ChannelVisibilityFromRound`` config.
        """
        return self._channel_message_count_at_round_start

    def snapshot_round_start(self, round_number: int) -> None:
        """Snapshot per-channel message counts as ``round_number`` begins.

        Called by the game clock right after emitting ``RoundAdvanced``.
        The snapshot is keyed by ``round_number``; subsequent calls for
        the same round overwrite the prior entry.
        """
        snapshot: dict[str, int] = {}
        for channel_id in self._channels_iter():
            snapshot[channel_id] = self._channel_router.get_message_count(channel_id=channel_id)
        self._channel_message_count_at_round_start[round_number] = snapshot

    def seed_round_snapshots(self, snapshots: dict[int, dict[str, int]]) -> None:
        """Pre-populate the round-start snapshots from a resumed run's history.

        Called once on resume so that ``ChannelVisibilityFromRound``
        lookups in subsequent in-run swaps can reference rounds that
        ran in the source simulation.
        """
        self._channel_message_count_at_round_start.update(snapshots)

    def _channels_iter(self) -> list[str]:
        """Return the list of channel IDs currently registered with the router."""
        return [ch_id for ch_id in self._channel_router.get_all_messages()]

    def update_agent_config(self, agent_id: str, config: AgentConfig) -> None:
        """Replace the stored ``AgentConfig`` for an agent (used by mid-run swaps).

        Discards any cached token counter for the agent so the next
        ``count_tokens`` call rebuilds it for the new model/provider.
        """
        self._agent_configs_by_id[agent_id] = config
        self._token_counters.pop(agent_id, None)

    def replace_agent_session(self, agent_id: str, session: AgentSession) -> None:
        """Swap the active ``AgentSession`` for an agent (used by mid-run swaps)."""
        self._agent_sessions[agent_id] = session

    def get_agent_config(self, agent_id: str) -> AgentConfig:
        """Look up the active ``AgentConfig`` for an agent, raising if unknown."""
        config = self._agent_configs_by_id.get(agent_id)
        if config is None:
            raise ValueError(f"Unknown agent: {agent_id}")
        return config

    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        """Check whether an agent is authorized to call a scenario tool."""
        allowlist = self._agent_tool_allowlists.get(agent_id)
        if allowlist is None:
            return False
        return tool_name in allowlist

    async def count_tokens(self, agent_id: str, text: str) -> int:
        """Count tokens using the calling agent's provider-specific tokenizer.

        Creates and caches the token counter on first use for each agent.
        """
        counter = self._token_counters.get(agent_id)
        if counter is None:
            config = self._agent_configs_by_id[agent_id]
            counter = create_token_counter(
                provider=config.provider,
                model=config.model,
            )
            self._token_counters[agent_id] = counter
        return await counter.count(text=text)

    def notify_world_of_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Update world state synchronously, then enqueue the event for async processing."""
        self._scenario.get_world().on_message(
            agent_id=agent_id,
            channel_id=channel_id,
            text=text,
            token_count=token_count,
        )
        self._world_context.enqueue_message_event(
            agent_id=agent_id,
            channel_id=channel_id,
            text=text,
            token_count=token_count,
        )

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

"""Shared simulation state accessed by MCP tools and the game clock.

Holds channel state, per-agent notification queues, per-channel write locks,
per-agent tool authorization allowlists, world context, and event logging.
Does not define MCP tools; those live in ``mcp_tools``.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import NamedTuple
from uuid import uuid4

from glossogen.channel_router import ChannelRouter
from glossogen.event_logger import EventLogger
from glossogen.llm.token_counter import TokenCounter, create_token_counter
from glossogen.models.agent_config import AgentConfig
from glossogen.models.channel import Channel
from glossogen.models.event import InjectionDelivered, MessageSent, PostmortemStarted
from glossogen.models.interaction_protocol import is_workspace_action_protocol
from glossogen.models.message import SimulationMessage
from glossogen.runtime.activity_notification import (
    DoneNotification,
    NewInfoNotification,
    NewMessagesNotification,
)
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scenario_world import MessageEvent, WorldContext
from glossogen.runtime.virtual_clock import VirtualClock
from glossogen.runtime.wait_registry import WaitRegistry, asyncio_timer, monotonic_clock
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

WORKSPACE_ACTION_HIDDEN_BASE_TOOLS = frozenset(
    {"send_message", "read_channel", "list_channels", "get_channel_members"}
)
"""Base tools not listed for ``workspace_action`` agents; ``read_notifications`` stays."""


class PublishedMessage(NamedTuple):
    """A public message after it has been stored and announced."""

    message: SimulationMessage
    token_count: int


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
        simulation_start_time: datetime,
    ) -> None:
        self._scenario = scenario
        self._channel_router = ChannelRouter(channels=channels)
        self._event_logger = event_logger
        self._agent_sessions = agent_sessions
        self._agent_tool_allowlists = agent_tool_allowlists
        self._world_context = world_context
        self._current_round = 1
        self._simulation_start_time = simulation_start_time
        world_context.channel_router = self._channel_router
        world_context.get_current_round = lambda: self._current_round
        self._agent_configs_by_id = {c.agent_id: c for c in agent_configs}
        self._token_counters: dict[str, TokenCounter] = {}
        self._channel_locks: dict[str, asyncio.Lock] = {
            ch.channel_id: asyncio.Lock() for ch in channels
        }
        self._on_message_callbacks: list[Callable[[], None]] = []
        self._channel_message_count_at_round_start: dict[int, dict[str, int]] = {}
        self._last_injected_rounds: dict[str, int] = {}
        self._virtual_clock: VirtualClock | None = None
        virtual_clock_config = scenario.get_virtual_clock_config()
        if virtual_clock_config is None:
            self._wait_registry = WaitRegistry(
                channel_router=self._channel_router,
                agent_sessions=agent_sessions,
                current_round=lambda: self._current_round,
                schedule_timer=asyncio_timer,
                clock=monotonic_clock,
                on_park=None,
                on_resume=None,
            )
        else:
            clock = VirtualClock(config=virtual_clock_config, agent_ids=list(agent_sessions))
            self._virtual_clock = clock
            self._wait_registry = WaitRegistry(
                channel_router=self._channel_router,
                agent_sessions=agent_sessions,
                current_round=lambda: self._current_round,
                schedule_timer=clock.schedule_timer,
                clock=clock.time,
                on_park=clock.park,
                on_resume=clock.wake,
            )

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
    def current_round(self) -> int:
        """The simulation round number in effect right now.

        Written by the game clock when it logs a ``RoundAdvanced``, and by the
        supervisor when seeding round state on resume. Read by MCP tools,
        scenario hooks, the world context, and runners.
        """
        return self._current_round

    def set_current_round(self, round_number: int) -> None:
        """Update the active round number. Called by the game clock and the supervisor."""
        self._current_round = round_number

    @property
    def simulation_start_time(self) -> datetime:
        """UTC time the simulation began, used to express message times as elapsed seconds.

        Set once at construction: to ``now`` on a fresh run, or to the original
        run's ``SimulationStarted`` timestamp on resume, so elapsed values stay
        anchored to the same origin across a resume boundary.
        """
        return self._simulation_start_time

    @property
    def agent_sessions(self) -> dict[str, AgentSession]:
        """Access per-agent sessions."""
        return self._agent_sessions

    def get_channel_lock(self, channel_id: str) -> asyncio.Lock:
        """Return the write lock for a channel."""
        return self._channel_locks[channel_id]

    @property
    def wait_registry(self) -> WaitRegistry:
        """Where suspended ``workspace_action`` agents are parked and resumed."""
        return self._wait_registry

    @property
    def virtual_clock(self) -> VirtualClock | None:
        """The simulated-API clock, or None when the run keeps wall-clock pace."""
        return self._virtual_clock

    async def record_public_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
        recipient_agent_ids: list[str] | None = None,
        reply_to: str | None = None,
    ) -> PublishedMessage:
        """Store one channel message, log it, and announce it to the other members.

        The caller holds the channel's write lock and has already validated the
        send. The text is passed through the scenario's outgoing transform.
        Members on the ``workspace_action`` protocol receive messages inside tool
        results, so only the others get a ``new_messages`` notification. Parked
        agents are re-evaluated last, after the message is in the history their
        conditions read.
        """
        transformed_text = self._scenario.transform_outgoing_message(
            agent_id=agent_id,
            channel_id=channel_id,
            text=text,
        )
        message = SimulationMessage(
            message_id=str(uuid4()),
            channel_id=channel_id,
            sender_agent_id=agent_id,
            sender_display_name=self._scenario.get_agent_display_name_at_round(
                agent_id=agent_id,
                round_number=self._current_round,
            ),
            text=transformed_text,
            recipient_agent_ids=recipient_agent_ids,
            reply_to=reply_to,
            timestamp=datetime.now(tz=UTC),
            round_number=self._current_round,
        )
        self._channel_router.append_message(message=message)
        await self._event_logger.log(
            event=MessageSent(
                message=message,
                round_number=self._current_round,
                token_count=token_count,
            )
        )
        for member_id in self._channel_router.get_channel_member_ids(channel_id=channel_id):
            if member_id == agent_id or not message.visible_to(member_id):
                continue
            member_session = self._agent_sessions.get(member_id)
            if member_session is None:
                continue
            member_config = self.get_agent_config(agent_id=member_id)
            if not is_workspace_action_protocol(member_config.interaction_protocol):
                member_session.push_notification(
                    notification=NewMessagesNotification(channels=[channel_id]),
                )
        self.fire_on_message_callbacks()
        self._wait_registry.publish_channel_message(channel_id=channel_id)
        return PublishedMessage(message=message, token_count=token_count)

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

    def agent_configs(self) -> list[AgentConfig]:
        """Every agent's active config, in registration order."""
        return list(self._agent_configs_by_id.values())

    def get_agent_config(self, agent_id: str) -> AgentConfig:
        """Look up the active ``AgentConfig`` for an agent, raising if unknown."""
        config = self._agent_configs_by_id.get(agent_id)
        if config is None:
            raise ValueError(f"Unknown agent: {agent_id}")
        return config

    def drain_unread_channel_messages(
        self, agent_id: str, channel_id: str
    ) -> list[SimulationMessage]:
        """Return unread visible messages once and advance the agent's read cursor."""
        if not self._channel_router.validate_membership(
            agent_id=agent_id,
            channel_id=channel_id,
        ):
            raise ValueError(f"Agent '{agent_id}' is not a member of channel '{channel_id}'")
        session = self.resolve_session(agent_id=agent_id)
        actual_count = self._channel_router.get_message_count(channel_id=channel_id)
        last_seen = session.get_last_seen_count(channel_id=channel_id)
        if actual_count <= last_seen:
            return []
        history = self._channel_router.get_history(channel_id=channel_id)
        unread = [m for m in history[last_seen:actual_count] if m.visible_to(agent_id)]
        session.record_channel_read(channel_id=channel_id, message_count=actual_count)
        return unread

    def is_base_tool_hidden(self, agent_id: str, tool_name: str) -> bool:
        """Whether ``tool_name`` is a channel tool withheld from a ``workspace_action`` agent.

        Such an agent messages with ``send`` and reads messages in tool results,
        so ``send_message`` and the channel browsing tools are not listed for it.
        """
        config = self._agent_configs_by_id.get(agent_id)
        if config is None or not is_workspace_action_protocol(config.interaction_protocol):
            return False
        return tool_name in WORKSPACE_ACTION_HIDDEN_BASE_TOOLS

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

    async def notify_world_of_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Update world state, then let the world react, before the send returns.

        The world sees a message twice: once for state the sending agent must
        observe on its own turn, and once for the reactions, which is where
        budget notifications come from. Both happen here, in that order, while
        the sender waits.

        The reaction used to run on the world's own task, which left the
        counter and the check reading different moments: two messages sent
        close together could both land before either was reacted to, and a team
        that should have been warned at 75% of its budget was warned only once
        it was spent. Which warnings a team got then depended on how the loop
        interleaved, so a run could not be reproduced.
        """
        world = self._scenario.get_world()
        world.on_message(
            agent_id=agent_id,
            channel_id=channel_id,
            text=text,
            token_count=token_count,
        )
        await world.on_message_async(
            event=MessageEvent(
                agent_id=agent_id,
                channel_id=channel_id,
                text=text,
                token_count=token_count,
            ),
            context=self._world_context,
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
        if self._virtual_clock is not None:
            # A response still waiting for its virtual turn would otherwise
            # never be released, and its runner would never read the done.
            self._virtual_clock.stop()

    def seed_last_injected_rounds(self, injected_rounds: dict[str, int]) -> None:
        """Seed per-agent last-injected round numbers from a resumed run's state.

        Subsequent ``deliver_round_injections`` calls skip any agent whose
        round number is already covered, so injections delivered in the
        source run are not re-emitted on resume.
        """
        self._last_injected_rounds = dict(injected_rounds)

    def has_postmortem_for_round(self, round_number: int) -> bool:
        """True if any agent has a postmortem injection scheduled for ``round_number``."""
        for agent_id in self._agent_sessions:
            injection = self._scenario.get_postmortem_injection(
                round_number=round_number,
                agent_id=agent_id,
            )
            if injection is not None:
                return True
        return False

    async def deliver_round_injections(self, round_number: int) -> None:
        """Push round injections to every agent that has one for ``round_number``.

        Skips agents whose ``_last_injected_rounds`` entry already covers
        this round (set during resume).
        """
        for agent_id, session in self._agent_sessions.items():
            already_injected_round = self._last_injected_rounds.get(agent_id, 0)
            if round_number <= already_injected_round:
                logger.debug(
                    "Skipping injection for %s round %d (already delivered up to round %d)",
                    agent_id,
                    round_number,
                    already_injected_round,
                )
                continue

            injection_text = self._scenario.get_injection(
                round_number=round_number,
                agent_id=agent_id,
            )
            if not injection_text:
                continue

            session.push_notification(
                notification=NewInfoNotification(text=injection_text),
            )
            await self._event_logger.log(
                event=InjectionDelivered(
                    agent_id=agent_id,
                    round_number=round_number,
                    text=injection_text,
                )
            )
            logger.debug(
                "Injection delivered to %s for round %d",
                agent_id,
                round_number,
            )

    async def deliver_postmortem_injections(self, round_number: int) -> None:
        """Log ``PostmortemStarted`` and push postmortem injections to agents.

        Phase-transition state (the clock's ``_in_postmortem`` flag, timing
        resets) is set by the caller before invoking this method.
        """
        await self._event_logger.log(
            event=PostmortemStarted(round_number=round_number),
        )
        self._scenario.on_postmortem_started(round_number=round_number)
        logger.info("Postmortem started for round %d", round_number)

        for agent_id, session in self._agent_sessions.items():
            injection_text = self._scenario.get_postmortem_injection(
                round_number=round_number,
                agent_id=agent_id,
            )
            if not injection_text:
                continue

            session.push_notification(
                notification=NewInfoNotification(text=injection_text),
            )
            await self._event_logger.log(
                event=InjectionDelivered(
                    agent_id=agent_id,
                    round_number=round_number,
                    text=injection_text,
                ),
            )
            logger.debug(
                "Postmortem injection delivered to %s for round %d",
                agent_id,
                round_number,
            )

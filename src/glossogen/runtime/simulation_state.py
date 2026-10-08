"""Shared simulation state accessed by MCP tools and the game clock.

Holds channel state, per-agent notification queues, per-channel write locks,
per-agent tool authorization allowlists, world context, and event logging.
Does not define MCP tools; those live in ``mcp_tools``.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from glossogen.channel_router import ChannelRouter
from glossogen.elapsed_time import elapsed_seconds_since_start
from glossogen.event_logger import EventLogger
from glossogen.llm.token_counter import TokenCounter, create_token_counter
from glossogen.models.agent_config import AgentConfig
from glossogen.models.channel import DIRECT_CHANNEL_PREFIX, Channel
from glossogen.models.event import (
    ChannelCreated,
    InjectionDelivered,
    MessageSent,
    PostmortemStarted,
)
from glossogen.models.mcp_responses import ChannelMessage, SendMessageResult
from glossogen.models.message import SimulationMessage
from glossogen.models.unread_channel_messages import UnreadChannelMessages
from glossogen.runtime.activity_notification import (
    DoneNotification,
    NewInfoNotification,
    NewMessagesNotification,
)
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scenario_world import MessageEvent, WorldContext
from glossogen.runtime.wait_registry import WaitRegistry
from glossogen.scenario_protocol import SimulationScenario

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
        self._wait_registry = WaitRegistry(
            channel_router=self._channel_router,
            session_for=self.resolve_session,
            schedule_wait_timeout=lambda agent_id, timeout_s, fire: (
                scenario.schedule_wait_timeout(agent_id=agent_id, timeout_s=timeout_s, fire=fire)
            ),
            clock=scenario.clock_now_s,
            on_park=lambda agent_id: scenario.on_agent_parked(agent_id=agent_id),
            on_resume=lambda agent_id: scenario.on_agent_resumed(agent_id=agent_id),
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

    @property
    def wait_registry(self) -> WaitRegistry:
        """Where agents parked in ``read_notifications`` wait to be resumed."""
        return self._wait_registry

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

    def is_base_tool_hidden(self, agent_id: str, tool_name: str) -> bool:
        """Whether the scenario withholds the base tool ``tool_name`` from ``agent_id``."""
        return tool_name in self._scenario.hidden_base_tools(agent_id=agent_id)

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

    async def publish_message(
        self, agent_id: str, channel_id: str, text: str, force: bool
    ) -> SendMessageResult:
        """Post ``text`` from ``agent_id`` to ``channel_id`` and tell the other members.

        Refuses a channel the agent does not belong to with ``ValueError``. Returns
        ``rejected`` when the scenario's ``validate_outgoing_message`` refuses the
        send, and ``conflict`` with the unseen messages when the channel moved
        since the agent last read it, unless ``force``. Otherwise stores the
        scenario-transformed text, logs ``message_sent``, notifies the other
        members and the world. The sender's read position moves past its own
        message only when it had read everything before it.
        """
        if not self._channel_router.validate_membership(agent_id=agent_id, channel_id=channel_id):
            raise ValueError(f"You are not a member of channel '{channel_id}'")
        rejection_reason = self._scenario.validate_outgoing_message(
            agent_id=agent_id, channel_id=channel_id
        )
        if rejection_reason is not None:
            return SendMessageResult(
                status="rejected",
                detail=rejection_reason,
                new_messages=[],
                token_count=0,
                current_round=self._current_round,
                message_id=None,
            )
        # Count tokens before acquiring the lock to avoid holding the lock
        # during a potentially slow external API call.
        token_count = await self.count_tokens(agent_id=agent_id, text=text)
        session = self.resolve_session(agent_id=agent_id)
        async with self.get_channel_lock(channel_id=channel_id):
            last_seen = session.get_last_seen_count(channel_id=channel_id)
            if (
                not force
                and self._channel_router.get_message_count(channel_id=channel_id) > last_seen
            ):
                return self._conflict_result(
                    agent_id=agent_id, channel_id=channel_id, last_seen=last_seen
                )
            message = await self._store_message(
                session=session, channel_id=channel_id, text=text, token_count=token_count
            )
        await self.notify_world_of_message(
            agent_id=agent_id, channel_id=channel_id, text=text, token_count=token_count
        )
        logger.info("Agent %s sent %d tokens to channel %s", agent_id, token_count, channel_id)
        return SendMessageResult(
            status="sent",
            detail=f"Message sent to channel '{channel_id}'",
            new_messages=[],
            token_count=token_count,
            current_round=self._current_round,
            message_id=message.message_id,
        )

    def _conflict_result(self, agent_id: str, channel_id: str, last_seen: int) -> SendMessageResult:
        """The ``conflict`` answer carrying the visible messages the sender has not seen."""
        history = self._channel_router.get_history(channel_id=channel_id)
        visible = self._channel_router.get_visible_history(channel_id=channel_id, agent_id=agent_id)
        unseen = history[max(last_seen, len(history) - len(visible)) :]
        logger.info(
            "Agent %s send_message conflict on channel %s: last_seen=%d (%d new)",
            agent_id,
            channel_id,
            last_seen,
            len(unseen),
        )
        return SendMessageResult(
            status="conflict",
            detail=(
                f"{len(unseen)} new message(s) arrived since your last read. "
                "Review them and either revise your message or re-send with force=true."
            ),
            new_messages=[
                ChannelMessage(
                    round=message.round_number,
                    sender=message.sender_display_name,
                    text=message.text,
                    elapsed_seconds=elapsed_seconds_since_start(
                        when=message.timestamp, start=self._simulation_start_time
                    ),
                )
                for message in unseen
            ],
            token_count=0,
            current_round=self._current_round,
            message_id=None,
        )

    async def _store_message(
        self, session: AgentSession, channel_id: str, text: str, token_count: int
    ) -> SimulationMessage:
        """Append and log one message, then tell every other member of the channel.

        The sender's read position moves past its own message only when it had
        read everything before it. A forced send over messages the sender has not
        seen leaves them unread, so they are still delivered to it.
        """
        agent_id = session.agent_id
        was_up_to_date = session.get_last_seen_count(
            channel_id=channel_id
        ) == self._channel_router.get_message_count(channel_id=channel_id)
        message = SimulationMessage(
            message_id=str(uuid4()),
            channel_id=channel_id,
            sender_agent_id=agent_id,
            sender_display_name=self._scenario.get_agent_display_name_at_round(
                agent_id=agent_id, round_number=self._current_round
            ),
            text=self._scenario.transform_outgoing_message(
                agent_id=agent_id, channel_id=channel_id, text=text
            ),
            timestamp=datetime.now(tz=UTC),
            round_number=self._current_round,
        )
        self._channel_router.append_message(message=message)
        await self._event_logger.log(
            event=MessageSent(
                message=message, round_number=self._current_round, token_count=token_count
            )
        )
        if was_up_to_date:
            session.record_channel_read(
                channel_id=channel_id,
                message_count=self._channel_router.get_message_count(channel_id=channel_id),
            )
        for member_id in self._channel_router.get_channel_member_ids(channel_id=channel_id):
            member_session = self._agent_sessions.get(member_id)
            if member_id != agent_id and member_session is not None:
                member_session.push_notification(
                    notification=NewMessagesNotification(channels=[channel_id])
                )
        self.fire_on_message_callbacks()
        return message

    async def direct_channel_for(self, agent_id: str, recipient_agent_ids: list[str]) -> str:
        """Return the channel whose members are ``agent_id`` and ``recipient_agent_ids``.

        A primary channel with exactly those members is returned as is, so
        addressing everyone on it posts there. Otherwise the direct channel
        ``dm:<sorted ids joined by +>`` is returned, created and logged with
        ``channel_created`` the first time. Raises ``ValueError`` for an empty list,
        the sender among the recipients, a recipient not in the simulation, or a
        request the scenario's ``validate_direct_channel`` refuses.
        """
        if not recipient_agent_ids:
            raise ValueError("Name at least one teammate to address.")
        for recipient in recipient_agent_ids:
            if recipient == agent_id or recipient not in self._agent_configs_by_id:
                raise ValueError(f"'{recipient}' is not a teammate you can address.")
        rejection_reason = self._scenario.validate_direct_channel(
            agent_id=agent_id, recipient_agent_ids=list(recipient_agent_ids)
        )
        if rejection_reason is not None:
            raise ValueError(rejection_reason)
        participants = sorted({agent_id, *recipient_agent_ids})
        for primary in self._scenario.get_primary_channels():
            members = self._channel_router.get_channel_member_ids(channel_id=primary.channel_id)
            if sorted(members) == participants:
                return primary.channel_id
        direct_channel_id = DIRECT_CHANNEL_PREFIX + "+".join(participants)
        if self._channel_router.channel_exists(channel_id=direct_channel_id):
            return direct_channel_id
        channel = Channel(
            channel_id=direct_channel_id,
            name="Direct: "
            + ", ".join(self._scenario.get_agent_display_name(agent_id=p) for p in participants),
            member_agent_ids=participants,
        )
        self.restore_created_channel(channel=channel)
        await self._event_logger.log(
            event=ChannelCreated(
                round_number=self._current_round,
                channel_id=channel.channel_id,
                name=channel.name,
                member_agent_ids=channel.member_agent_ids,
            )
        )
        logger.info("Created direct channel %s", channel.channel_id)
        return channel.channel_id

    def restore_created_channel(self, channel: Channel) -> None:
        """Add a channel created during a run, without logging it.

        The live path logs ``channel_created`` itself once the channel is new;
        a resumed run replays the source's event.
        """
        if self._channel_router.channel_exists(channel_id=channel.channel_id):
            return
        self._channel_router.add_channel(channel=channel)
        self._channel_locks[channel.channel_id] = asyncio.Lock()

    def drain_unread_channel_messages(self, agent_id: str) -> list[UnreadChannelMessages]:
        """Every message visible to ``agent_id`` that it has not read, grouped by channel.

        Channels come in channel-id order, and only channels with unread
        messages are returned. The agent's read position on each channel moves
        to the end, so the same messages are not returned twice.
        """
        session = self.resolve_session(agent_id=agent_id)
        drained: list[UnreadChannelMessages] = []
        for channel_id in sorted(self._channel_router.get_agent_channel_ids(agent_id=agent_id)):
            history = self._channel_router.get_history(channel_id=channel_id)
            visible = self._channel_router.get_visible_history(
                channel_id=channel_id, agent_id=agent_id
            )
            first_visible = len(history) - len(visible)
            start = max(session.get_last_seen_count(channel_id=channel_id), first_visible)
            session.record_channel_read(channel_id=channel_id, message_count=len(history))
            if start < len(history):
                drained.append(
                    UnreadChannelMessages(channel_id=channel_id, messages=history[start:])
                )
        return drained

    def broadcast_done(self, reason: str) -> None:
        """Tell the scenario the run is stopping, then push a done notification to all agents."""
        logger.info(
            "Broadcasting done to %d agents: %s",
            len(self._agent_sessions),
            reason,
        )
        self._scenario.on_simulation_stopping()
        for session in self._agent_sessions.values():
            session.push_notification(
                notification=DoneNotification(reason=reason),
            )

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

        Every agent is notified before any delivery is logged, so the briefings
        reach the agents at one point of the event loop and a scenario clock sees
        every agent woken at the same instant. Skips agents whose
        ``_last_injected_rounds`` entry already covers this round (set during
        resume).
        """
        delivered: list[tuple[str, str]] = []
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
                notification=NewInfoNotification(text=injection_text, kind="injection"),
            )
            delivered.append((agent_id, injection_text))
        for agent_id, injection_text in delivered:
            await self._event_logger.log(
                event=InjectionDelivered(
                    agent_id=agent_id,
                    round_number=round_number,
                    text=injection_text,
                )
            )
            logger.debug("Injection delivered to %s for round %d", agent_id, round_number)

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
                notification=NewInfoNotification(text=injection_text, kind="injection"),
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

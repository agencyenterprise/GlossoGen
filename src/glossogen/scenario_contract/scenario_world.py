"""The world simulation a scenario runs alongside its agents.

Every scenario provides a ``ScenarioWorld`` that runs as its own asyncio task.
The world receives message events and round advance signals via a ``WorldContext``,
and can push channel-scoped notifications via ``send_update_to_channel``. The
runtime implements the context in :mod:`glossogen.runtime.world_context`.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import NamedTuple


class MessageEvent(NamedTuple):
    """Delivered to the world when an agent sends a message."""

    agent_id: str
    channel_id: str
    text: str
    token_count: int


class RoundAdvancedEvent(NamedTuple):
    """Delivered to the world when the game clock advances to a new round."""

    round_number: int


class WorldContext(ABC):
    """What a world simulation reaches the running simulation through.

    The runtime implements it and passes it to the world's ``run`` method. The
    world awaits ``next_event`` to receive round transitions, and calls
    ``send_update_to_channel`` or ``send_update_to_agent`` to notify agents.
    """

    @abstractmethod
    async def next_event(self) -> RoundAdvancedEvent:
        """Block until the next round advance."""

    @abstractmethod
    async def send_update_to_channel(self, channel_id: str, text: str) -> None:
        """Push a world notification only to agents in the specified channel.

        Agents outside the channel do not receive the notification. One
        ``WorldEventDelivered`` event is logged per delivered agent.
        """

    @abstractmethod
    async def send_update_to_agent(self, agent_id: str, text: str) -> None:
        """Push a world notification to a single agent and log one ``WorldEventDelivered``."""

    @abstractmethod
    async def update_channel_members(
        self,
        channel_id: str,
        member_agent_ids: list[str],
        reason: str,
    ) -> None:
        """Replace a channel's member list and log the change.

        The change takes effect for every later ``send_message`` and
        ``read_channel`` call. Messages sent before an agent joined do not count
        as unread for it.
        """

    @abstractmethod
    async def clear_channel_history(self, channel_id: str, reason: str) -> None:
        """Wipe a channel's message history; messages appended after it count as new."""


class ScenarioWorld(ABC):
    """A living world simulation that runs alongside agents as its own asyncio task.

    Scenarios subclass this to define dynamic world behavior: real-time state
    changes, environmental updates, and reactive events based on agent
    communication. Message handling is split in two: ``on_message`` runs
    synchronously for immediate state mutation, and ``on_message_async`` is
    awaited right after it for side-effects such as notifications; both run
    while the sending agent waits. Both default to no-ops, so a world that only
    tracks state accessed via other methods needs to override neither.

    The ``run`` event loop is provided by the platform; it is started as an
    asyncio task by the supervisor and cancelled when the simulation ends.

    Postmortem state lives here too. A postmortem phase is a platform concept:
    the game clock opens and closes it, and the in-run swap logic asks which
    channels are dead. Subclasses declare which of their channels carry
    postmortem traffic and get the phase tracking from this class.
    """

    def __init__(
        self,
        postmortem_channel_ids: frozenset[str],
        postmortem_globally_disabled: bool,
    ) -> None:
        """Record the postmortem channels and whether they start closed.

        ``postmortem_channel_ids`` is empty for a scenario with no postmortem,
        which makes every method below a no-op without special-casing.
        """
        self._postmortem_channel_ids = postmortem_channel_ids
        self._postmortem_globally_disabled = postmortem_globally_disabled
        self._in_postmortem = False

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is in a postmortem discussion phase."""
        return self._in_postmortem

    @property
    def is_postmortem_disabled(self) -> bool:
        """Whether postmortem has been globally disabled."""
        return self._postmortem_globally_disabled

    def enter_postmortem(self) -> None:
        """Mark the start of a postmortem discussion phase."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Mark the end of a postmortem discussion phase."""
        self._in_postmortem = False

    def bind_context(self, context: WorldContext) -> None:
        """Attach the context the world sends updates through.

        Called when the world is wired, before its task is created. Binding
        inside ``run`` instead leaves a window: ``create_task`` schedules the
        coroutine without running it, so a tool call arriving before the task is
        first scheduled finds no context and fails.
        """
        self._world_context = context

    async def run(self, context: WorldContext) -> None:
        """Drain the round-advance events the game clock enqueues.

        They are drained without action: scenarios handle round transitions
        through ``SimulationScenario.on_round_advanced``, and a send awaits the
        world's reaction directly. Started as an asyncio task by the supervisor
        and cancelled at simulation end.
        """
        self.bind_context(context=context)
        try:
            while True:
                await context.next_event()
        except asyncio.CancelledError:
            return

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Called from ``publish_message`` while the sender waits, before ``on_message_async``.

        Override this to update world state that must be visible immediately
        (e.g. token accumulation, patient death). The default is a no-op.
        Asynchronous side-effects belong in ``on_message_async`` instead.
        """
        _ = agent_id, channel_id, text, token_count

    async def on_message_async(self, event: MessageEvent, context: WorldContext) -> None:
        """React asynchronously to an agent message, after ``on_message``.

        Called once per message, while the sender waits. Override to push channel- or agent-scoped
        notifications via ``context`` (e.g. budget-threshold warnings). The
        default is a no-op. Synchronous state updates belong in ``on_message``.
        """
        _ = event, context

    def get_globally_disabled_channels(self) -> frozenset[str]:
        """Return channel IDs that have been globally disabled for the rest of the run.

        The runtime treats these channels as effectively dead for any
        agent swapped in via the in-run scheduler: the swap logic forces
        ``ChannelVisibilityNone`` on them (history hidden, predecessor
        tool calls dropped) and excludes them from the wake-up
        notification so the new agent does not get spurious "you have
        new messages" alerts on a channel they shouldn't be reading.
        """
        if not self._postmortem_globally_disabled:
            return frozenset()
        return self._postmortem_channel_ids

    def disable_postmortem_globally(self) -> None:
        """Close the postmortem channel(s) for the rest of the simulation.

        Invoked by the autonomous supervisor when a ``set_postmortem``
        scheduled event fires. A scenario that declared no postmortem
        channels is unaffected: the flag is set and the disabled set stays
        empty.
        """
        self._postmortem_globally_disabled = True

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

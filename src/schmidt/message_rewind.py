"""Reconstructs simulation state at any message for rewind-and-fork.

Given a target ``MessageSent`` event, replays the event log up to that point
and extracts everything needed to resume the simulation: channel messages,
current round, delivered injections, and agent/scenario metadata.

State reconstruction (channels, injections, current round) is always
timestamp-anchored: every event with ``timestamp <= target_timestamp``
is replayed, including the boundary ``RoundAdvanced`` whose timestamp
equals the anchor — so the resumed simulation knows it has just entered
``round_start``. Per-agent history reconstruction additionally accepts
a ``cutoff_round`` (set by the replace-agent flow): individual tool
calls are kept iff their own ``ToolCallInvoked.round_number <
cutoff_round``, which preserves pre-anchor calls whose parent
``LLMResponseReceived`` was logged after the anchor because the LLM
cycle straddled a round boundary. Fork and ``--resume`` callers pass
``cutoff_round=None`` and fall back to the same timestamp filter at
the per-call level.
"""

import logging
from datetime import datetime
from typing import Any, NamedTuple

from pydantic_ai.messages import ModelMessage

from schmidt.message_history_builder import build_message_history
from schmidt.models.event import (
    AgentRegistered,
    InjectionDelivered,
    MessageSent,
    RoundAdvanced,
    SimulationEvent,
    SimulationStarted,
)
from schmidt.models.message import SimulationMessage
from schmidt.runners.communication_protocol import build_full_system_prompt
from schmidt.runtime.scheduled_events import ChannelVisibility

logger = logging.getLogger(__name__)


class ImportedHistory(NamedTuple):
    """Redirect for an agent's history reconstruction to a different event stream.

    Used by the cross-run replace-agent flow to import an agent from a
    different completed run. When attached to an ``AgentHistoryFilter``,
    the per-agent history is built from ``events`` up to
    ``target_timestamp`` with ``cutoff_round`` driving the per-tool-call
    filter, and the ``AgentRegistered`` for that agent inside ``events``
    supplies the system prompt. The state walk (channels, injections,
    current round) still uses the caller's primary event list.
    """

    events: tuple[SimulationEvent, ...]
    target_timestamp: datetime
    cutoff_round: int


class AgentHistoryFilter(NamedTuple):
    """Per-agent filter applied while reconstructing pydantic-ai history.

    ``tool_calls_only`` strips text and thinking parts from the agent's
    prior responses; only tool call parts survive. ``channel_visibility``
    maps channel_id to a ``ChannelVisibility`` variant — ``Full`` keeps
    every send/read tool call on that channel, ``None`` drops them all,
    ``FromRound(R)`` drops every ``read_channel`` and drops
    ``send_message`` calls with ``ToolCallInvoked.round_number < R``.
    Channels absent from the dict default to ``Full``. ``imported``
    redirects history reconstruction to a different event stream (see
    ``ImportedHistory``); when ``None`` the agent's history is built
    from the caller's primary event list.
    """

    tool_calls_only: bool
    channel_visibility: dict[str, ChannelVisibility]
    imported: ImportedHistory | None


_PASS_THROUGH_FILTER = AgentHistoryFilter(
    tool_calls_only=False,
    channel_visibility={},
    imported=None,
)


class RewindState(NamedTuple):
    """Everything needed to resume a simulation from a specific message.

    ``replaced_agent_ids`` lists agents whose channel-history visibility
    must be reconfigured on resume (replace-agent flow). Empty for plain
    `--resume` and fork.

    ``replaced_agent_channel_visibility`` maps agent_id to a per-channel
    visibility config. The supervisor consults this map and the
    ``channel_message_count_at_round_start`` snapshot to compute each
    replaced agent's ``member_join_index`` per channel on resume. Channels
    not listed in the inner dict are left untouched (preserve existing
    visibility). Defaults to an empty mapping for `--resume`/fork flows.

    ``channel_message_count_at_round_start`` snapshots, per round,
    how many ``MessageSent`` events had appeared on each channel before
    the ``RoundAdvanced(round_number)`` anchor. Used to translate
    ``ChannelVisibilityFromRound(R)`` into a concrete
    ``member_join_index`` for windowed channel visibility on a
    swapped-in agent.
    """

    round_number: int
    messages_by_channel: dict[str, list[SimulationMessage]]
    injected_rounds: dict[str, int]
    scenario_name: str
    scenario_config: dict[str, Any]
    agent_registrations: list[AgentRegistered]
    agent_message_histories: dict[str, list[ModelMessage]]
    replaced_agent_ids: frozenset[str]
    replaced_agent_channel_visibility: dict[str, dict[str, ChannelVisibility]]
    channel_message_count_at_round_start: dict[int, dict[str, int]]


def build_rewind_state(
    events: list[SimulationEvent],
    target_message_id: str,
    message_edits: dict[str, str],
    agent_filters: dict[str, AgentHistoryFilter],
    cutoff_round: int | None,
) -> RewindState:
    """Build state at a specific message, optionally applying text edits.

    ``agent_filters`` lets callers customize each agent's reconstructed
    pydantic-ai history. Agents not in the dict get the default
    pass-through filter (full history). ``cutoff_round`` is forwarded
    to the state walk and history builder; pass ``None`` for fork /
    ``--resume`` flows that anchor on a message timestamp.

    Raises:
        ValueError: If no ``MessageSent`` event with the target ID is found.
    """
    target_timestamp = _find_message_timestamp(
        events=events,
        target_message_id=target_message_id,
    )
    return _build_rewind_state_at_timestamp(
        events=events,
        target_timestamp=target_timestamp,
        cutoff_round=cutoff_round,
        message_edits=message_edits,
        agent_filters=agent_filters,
    )


def build_rewind_state_at_event(
    events: list[SimulationEvent],
    target_event_id: str,
    cutoff_round: int | None,
    agent_filters: dict[str, AgentHistoryFilter],
) -> RewindState:
    """Build rewind state targeting any event by ``event_id``.

    Used by the replace-agent resume path to anchor at a ``RoundAdvanced``
    event (no associated message_id). The walk includes the target event
    itself, so the resulting ``round_number`` reflects the round that has
    just started at the anchor. ``cutoff_round`` selects round-based
    filtering when set.

    Raises ``ValueError`` if no event with ``target_event_id`` exists.
    """
    target_timestamp = _find_event_timestamp(
        events=events,
        target_event_id=target_event_id,
    )
    return _build_rewind_state_at_timestamp(
        events=events,
        target_timestamp=target_timestamp,
        cutoff_round=cutoff_round,
        message_edits={},
        agent_filters=agent_filters,
    )


def _build_rewind_state_at_timestamp(
    events: list[SimulationEvent],
    target_timestamp: datetime,
    cutoff_round: int | None,
    message_edits: dict[str, str],
    agent_filters: dict[str, AgentHistoryFilter],
) -> RewindState:
    """Walk ``events`` up to the timestamp anchor and assemble a ``RewindState``.

    The state walk is timestamp-anchored regardless of ``cutoff_round``
    so the boundary ``RoundAdvanced`` (whose timestamp is the anchor) is
    included and the resumed run picks up at the correct round.
    ``cutoff_round`` is forwarded to the per-agent history builder for
    its per-tool-call round filter.
    """
    round_number = 0
    messages_by_channel: dict[str, list[SimulationMessage]] = {}
    injected_rounds: dict[str, int] = {}
    scenario_name = ""
    scenario_config: dict[str, Any] = {}
    agent_registrations: list[AgentRegistered] = []
    channel_count_at_round_start: dict[int, dict[str, int]] = {}
    running_channel_counts: dict[str, int] = {}

    for event in events:
        if event.timestamp > target_timestamp:
            break

        if isinstance(event, SimulationStarted):
            scenario_name = event.scenario_name
            scenario_config = event.scenario_config

        elif isinstance(event, AgentRegistered):
            agent_registrations.append(event)

        elif isinstance(event, RoundAdvanced):
            round_number = event.round_number
            channel_count_at_round_start[event.round_number] = dict(running_channel_counts)

        elif isinstance(event, InjectionDelivered):
            current = injected_rounds.get(event.agent_id, 0)
            if event.round_number > current:
                injected_rounds[event.agent_id] = event.round_number

        elif isinstance(event, MessageSent):
            msg = event.message
            if msg.message_id in message_edits:
                msg = SimulationMessage(
                    message_id=msg.message_id,
                    channel_id=msg.channel_id,
                    sender_agent_id=msg.sender_agent_id,
                    text=message_edits[msg.message_id],
                    timestamp=msg.timestamp,
                    round_number=msg.round_number,
                )
            channel_id = msg.channel_id
            if channel_id not in messages_by_channel:
                messages_by_channel[channel_id] = []
            messages_by_channel[channel_id].append(msg)
            running_channel_counts[channel_id] = running_channel_counts.get(channel_id, 0) + 1

    agent_message_histories: dict[str, list[ModelMessage]] = {}
    for reg in agent_registrations:
        history_filter = agent_filters.get(reg.agent_id, _PASS_THROUGH_FILTER)
        history_events: list[SimulationEvent]
        history_target_timestamp: datetime
        history_cutoff_round: int | None
        if history_filter.imported is not None:
            history_events = list(history_filter.imported.events)
            history_target_timestamp = history_filter.imported.target_timestamp
            history_cutoff_round = history_filter.imported.cutoff_round
            imported_registration = _find_imported_registration(
                events=history_events,
                agent_id=reg.agent_id,
            )
            system_prompt = build_full_system_prompt(
                base_prompt=imported_registration.system_prompt,
                role_name=imported_registration.role_name,
            )
        else:
            history_events = events
            history_target_timestamp = target_timestamp
            history_cutoff_round = cutoff_round
            system_prompt = build_full_system_prompt(
                base_prompt=reg.system_prompt,
                role_name=reg.role_name,
            )
        agent_message_histories[reg.agent_id] = build_message_history(
            events=history_events,
            agent_id=reg.agent_id,
            system_prompt=system_prompt,
            target_timestamp=history_target_timestamp,
            cutoff_round=history_cutoff_round,
            tool_calls_only=history_filter.tool_calls_only,
            channel_visibility=history_filter.channel_visibility,
        )

    logger.info(
        "Rewind state built: round=%d, channels=%d, messages=%d, agents=%d",
        round_number,
        len(messages_by_channel),
        sum(len(msgs) for msgs in messages_by_channel.values()),
        len(agent_registrations),
    )

    return RewindState(
        round_number=round_number,
        messages_by_channel=messages_by_channel,
        injected_rounds=injected_rounds,
        scenario_name=scenario_name,
        scenario_config=scenario_config,
        agent_registrations=agent_registrations,
        agent_message_histories=agent_message_histories,
        replaced_agent_ids=frozenset(),
        replaced_agent_channel_visibility={},
        channel_message_count_at_round_start=channel_count_at_round_start,
    )


def build_rewind_state_from_last_message(
    events: list[SimulationEvent],
    agent_filters: dict[str, AgentHistoryFilter],
) -> RewindState:
    """Build rewind state targeting the last MessageSent event in the log.

    Used by ``--resume`` in autonomous mode to pick up from where the
    simulation left off. No edits are applied. Falls back to the
    timestamp-based cutoff because ``--resume`` does not anchor on a
    round boundary.

    Raises ``ValueError`` if no ``MessageSent`` event exists in the log.
    """
    last_message_id: str | None = None
    for event in events:
        if isinstance(event, MessageSent):
            last_message_id = event.message.message_id

    if last_message_id is None:
        raise ValueError("No MessageSent events found in the log. Cannot resume.")

    return build_rewind_state(
        events=events,
        target_message_id=last_message_id,
        message_edits={},
        agent_filters=agent_filters,
        cutoff_round=None,
    )


def _find_message_timestamp(
    events: list[SimulationEvent],
    target_message_id: str,
) -> datetime:
    """Find the timestamp of the MessageSent event with the given message_id.

    Raises ``ValueError`` if no matching event exists.
    """
    for event in events:
        if isinstance(event, MessageSent) and event.message.message_id == target_message_id:
            return event.timestamp

    raise ValueError(
        f"No MessageSent event with message_id={target_message_id!r} found in the log."
    )


def _find_event_timestamp(
    events: list[SimulationEvent],
    target_event_id: str,
) -> datetime:
    """Find the timestamp of any event by ``event_id``.

    Raises ``ValueError`` if no matching event exists.
    """
    for event in events:
        if event.event_id == target_event_id:
            return event.timestamp

    raise ValueError(f"No event with event_id={target_event_id!r} found in the log.")


def _find_imported_registration(
    events: list[SimulationEvent],
    agent_id: str,
) -> AgentRegistered:
    """Locate the ``AgentRegistered`` event for ``agent_id`` inside an imported stream.

    Used when an ``AgentHistoryFilter`` redirects an agent's history
    reconstruction to a different run's events: the system prompt for the
    reconstructed history must come from that run, not the live one.

    Raises ``ValueError`` if no matching event exists.
    """
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id == agent_id:
            return event
    raise ValueError(
        f"No AgentRegistered event for agent_id={agent_id!r} in the imported event stream."
    )

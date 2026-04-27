"""Reconstructs simulation state at any message for rewind-and-fork.

Given a target ``MessageSent`` event, replays the event log up to that point
and extracts everything needed to resume the simulation: channel messages,
current round, delivered injections, and agent/scenario metadata.
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

logger = logging.getLogger(__name__)


class RewindState(NamedTuple):
    """Everything needed to resume a simulation from a specific message.

    ``replaced_agent_ids`` lists agents whose channel-history visibility
    must be wiped on resume (replace-agent flow). Empty for plain
    `--resume` and fork.

    ``replaced_agent_channels_with_visible_history`` maps agent_id to a
    list of channel IDs whose prior history should remain visible to that
    replaced agent. Channels of the replaced agent that are not in the
    list have their ``member_join_index`` bumped to the current message
    count on resume. Defaults to an empty mapping (= wipe every channel
    the agent is in, for callers that don't supply explicit visibility).
    """

    round_number: int
    messages_by_channel: dict[str, list[SimulationMessage]]
    injected_rounds: dict[str, int]
    scenario_name: str
    scenario_config: dict[str, Any]
    agent_registrations: list[AgentRegistered]
    agent_message_histories: dict[str, list[ModelMessage]]
    replaced_agent_ids: frozenset[str]
    replaced_agent_channels_with_visible_history: dict[str, list[str]]


def build_rewind_state(
    events: list[SimulationEvent],
    target_message_id: str,
    message_edits: dict[str, str],
) -> RewindState:
    """Build state at a specific message, optionally applying text edits.

    Args:
        events: Full event log from the simulation JSONL.
        target_message_id: The ``message_id`` of the ``MessageSent`` event
            to rewind to. All events up to and including this message are
            included in the reconstructed state.
        message_edits: Mapping of ``message_id`` to replacement text.
            Matched messages have their ``text`` field replaced.

    Raises:
        ValueError: If no ``MessageSent`` event with the target ID is found.
    """
    target_timestamp = _find_target_timestamp(
        events=events,
        target_message_id=target_message_id,
    )

    round_number = 0
    messages_by_channel: dict[str, list[SimulationMessage]] = {}
    injected_rounds: dict[str, int] = {}
    scenario_name = ""
    scenario_config: dict[str, Any] = {}
    agent_registrations: list[AgentRegistered] = []

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
                )
            channel_id = msg.channel_id
            if channel_id not in messages_by_channel:
                messages_by_channel[channel_id] = []
            messages_by_channel[channel_id].append(msg)

    agent_message_histories: dict[str, list[ModelMessage]] = {}
    for reg in agent_registrations:
        system_prompt = build_full_system_prompt(
            base_prompt=reg.system_prompt,
            role_name=reg.role_name,
        )
        agent_message_histories[reg.agent_id] = build_message_history(
            events=events,
            agent_id=reg.agent_id,
            system_prompt=system_prompt,
            target_timestamp=target_timestamp,
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
        replaced_agent_channels_with_visible_history={},
    )


def build_rewind_state_from_last_message(
    events: list[SimulationEvent],
) -> RewindState:
    """Build rewind state targeting the last MessageSent event in the log.

    Used by ``--resume`` in autonomous mode to pick up from where the
    simulation left off. No edits are applied.

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
    )


def _find_target_timestamp(
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

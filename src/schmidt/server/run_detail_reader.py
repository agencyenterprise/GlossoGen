"""Loads and parses a full JSONL simulation log into a RunDetailResponse."""

import logging
from pathlib import Path

from schmidt.evaluation.log_reader import load_events
from schmidt.models.event import (
    AgentRegistered,
    MessageSent,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
    TurnAssigned,
)
from schmidt.server.response_models import AgentDetail, MessageDetail, RunDetailResponse

logger = logging.getLogger(__name__)


def _derive_initials(role_name: str) -> str:
    """Derive two-letter uppercase initials from a role name.

    Uses the first letter of each word for multi-word names,
    or the first two letters for single-word names.
    """
    words = role_name.split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return role_name[:2].upper()


async def load_run_detail(log_path: Path) -> RunDetailResponse:
    """Parse all events from a JSONL log and assemble a RunDetailResponse."""
    events: list[SimulationEvent] = await load_events(log_path=log_path)

    run_id = ""
    scenario_name = ""
    timestamp = None
    channel_ids: list[str] = []
    agents: list[AgentDetail] = []
    messages: list[MessageDetail] = []
    total_turns = 0
    end_reason = None

    # Track the most recent TurnAssigned per agent
    agent_turn: dict[str, int] = {}
    agent_round: dict[str, int] = {}

    for event in events:
        if isinstance(event, SimulationStarted):
            run_id = event.event_id
            scenario_name = event.scenario_name
            timestamp = event.timestamp
            channel_ids = event.channel_ids

        elif isinstance(event, AgentRegistered):
            agents.append(
                AgentDetail(
                    agent_id=event.agent_id,
                    role_name=event.role_name,
                    initials=_derive_initials(role_name=event.role_name),
                    channel_ids=event.channel_ids,
                    tool_names=event.tool_names,
                    model=event.model,
                    system_prompt=event.system_prompt,
                )
            )

        elif isinstance(event, TurnAssigned):
            agent_turn[event.agent_id] = event.turn_number
            agent_round[event.agent_id] = event.round_number

        elif isinstance(event, MessageSent):
            msg = event.message
            messages.append(
                MessageDetail(
                    message_id=msg.message_id,
                    channel_id=msg.channel_id,
                    sender_agent_id=msg.sender_agent_id,
                    text=msg.text,
                    timestamp=msg.timestamp,
                    turn_number=agent_turn.get(msg.sender_agent_id, 0),
                    round_number=agent_round.get(msg.sender_agent_id, 0),
                )
            )

        elif isinstance(event, SimulationEnded):
            total_turns = event.total_turns
            end_reason = event.reason

    if timestamp is None:
        raise ValueError(f"No SimulationStarted event found in {log_path}")
    if end_reason is None:
        raise ValueError(f"No SimulationEnded event found in {log_path}")

    return RunDetailResponse(
        run_id=run_id,
        scenario_name=scenario_name,
        timestamp=timestamp,
        total_turns=total_turns,
        end_reason=end_reason,
        channel_ids=channel_ids,
        agents=agents,
        messages=messages,
    )

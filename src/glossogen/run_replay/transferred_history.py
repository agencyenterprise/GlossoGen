"""The history an agent carries into a run from another finished run.

A history-transfer run seats some of its agents with the history an agent built in
a source run, which may be of another scenario. That history is the source agent's
own: its system prompt, text, thinking, tool calls and tool results up to a round.
One user message follows it and opens the new run with the new run's system and
initial prompts. The model keeps the source's system prompt, because pydantic-ai
adds an agent's system prompt only to an empty history.

The history is built once, at launch, and saved in the run directory. A resumed run
reads it back and appends what the agent did in the run itself.
"""

import asyncio
from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)

from glossogen.models.event import SimulationEvent
from glossogen.run_replay.message_history_builder import build_message_history
from glossogen.run_replay.message_rewind import (
    RewindState,
    RoundEndCutoff,
    find_first_registration,
)
from glossogen.run_storage.history_transfer_manifest import read_history_transfer_manifest
from glossogen.scenario_contract.platform_runner_prompts import (
    build_full_system_prompt,
    registered_runner_prompts,
)


def build_source_history(
    source_events: list[SimulationEvent],
    source_agent_id: str,
    cutoff: RoundEndCutoff,
    split_parallel_tool_calls: bool,
) -> list[ModelMessage]:
    """Rebuild the source agent's turns up to ``cutoff``, with their text and thinking.

    The history opens with the source agent's own system prompt and initial prompt.

    Raises ``ValueError`` when the source agent took no turn before the cutoff.
    """
    registration = find_first_registration(events=source_events, agent_id=source_agent_id)
    runner_prompts = registered_runner_prompts(registration=registration)
    history = build_message_history(
        events=source_events,
        agent_id=source_agent_id,
        system_prompt=build_full_system_prompt(
            base_prompt=registration.system_prompt, prompts=runner_prompts
        ),
        runner_prompts=runner_prompts,
        target_timestamp=cutoff.timestamp,
        cutoff_round=cutoff.cutoff_round,
        tool_calls_only=False,
        channel_visibility={},
        history_floor_round=None,
        filter_below_round=None,
        split_parallel_tool_calls=split_parallel_tool_calls,
    )
    if not history:
        raise ValueError(
            f"source agent {source_agent_id!r} took no turn before round {cutoff.cutoff_round}"
        )
    return history


def build_transferred_history(
    source_events: list[SimulationEvent],
    source_agent_id: str,
    cutoff: RoundEndCutoff,
    opening_prompt: str,
    split_parallel_tool_calls: bool,
) -> list[ModelMessage]:
    """Build the history a seat starts with: the source agent's turns, then ``opening_prompt``.

    The trailing ``ModelRequest`` holds ``opening_prompt``; the runner sends it as
    the agent's first request.

    Raises ``ValueError`` when the source agent took no turn before the cutoff.
    """
    history = build_source_history(
        source_events=source_events,
        source_agent_id=source_agent_id,
        cutoff=cutoff,
        split_parallel_tool_calls=split_parallel_tool_calls,
    )
    return [*history, ModelRequest(parts=[UserPromptPart(content=opening_prompt)])]


async def write_transferred_history(path: Path, history: list[ModelMessage]) -> None:
    """Save ``history`` to ``path`` as pydantic-ai's JSON message format."""
    payload = ModelMessagesTypeAdapter.dump_json(history, indent=2)
    await asyncio.to_thread(path.write_bytes, payload)


async def read_transferred_history(path: Path) -> list[ModelMessage]:
    """Load a history saved by :func:`write_transferred_history`."""
    payload = await asyncio.to_thread(path.read_bytes)
    return ModelMessagesTypeAdapter.validate_json(payload)


def append_own_turns(
    transferred: list[ModelMessage], own_history: list[ModelMessage]
) -> list[ModelMessage]:
    """The transferred history followed by the agent's turns in this run.

    ``own_history`` is rebuilt from this run's log, so it opens with this run's
    system and initial prompts. The transferred history's last message replaced
    that opening for this agent, so it is dropped.
    """
    return [*transferred, *own_history[1:]]


async def splice_transferred_histories(run_dir: Path, state: RewindState) -> RewindState:
    """Put each transferred seat's saved history in front of its rebuilt turns.

    Returns ``state`` unchanged for a run without a history-transfer manifest.
    """
    manifest = read_history_transfer_manifest(run_dir=run_dir)
    if manifest is None:
        return state
    histories = dict(state.agent_message_histories)
    for seat in manifest.seats:
        transferred = await read_transferred_history(path=run_dir / seat.history_file)
        histories[seat.agent_id] = append_own_turns(
            transferred=transferred,
            own_history=histories.get(seat.agent_id, []),
        )
    return state._replace(agent_message_histories=histories)

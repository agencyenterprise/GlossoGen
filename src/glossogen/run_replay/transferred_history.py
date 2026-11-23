"""The history an agent carries into a run from another finished run.

A history-transfer run seats some of its agents with the history an agent built in
a source run, which may be of another scenario. That history is the source agent's
own: its system prompt, text, thinking, tool calls and tool results up to the cut.
One user message follows it and opens the new run with the new run's system and
initial prompts. The model keeps the source's system prompt, because pydantic-ai
adds an agent's system prompt only to an empty history.

The history is built once, at launch, and saved in the run directory. A resumed run,
the protocol probes and the thread export read it back and put it in front of what
the agent did in the run itself.
"""

import asyncio
from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    UserPromptPart,
)

from glossogen.models.event import AgentSwappedMidRun, SimulationEvent
from glossogen.run_replay.message_history_builder import build_message_history
from glossogen.run_replay.message_rewind import RewindState, find_first_registration
from glossogen.run_storage.history_transfer_manifest import (
    HistoryTransferManifest,
    read_history_transfer_manifest,
)
from glossogen.scenario_contract.platform_runner_prompts import registered_prompts


def build_source_history(
    source_events: list[SimulationEvent],
    source_agent_id: str,
    keep_thinking: bool,
    split_parallel_tool_calls: bool,
) -> list[ModelMessage]:
    """Rebuild the source agent's turns from ``source_events``, the source log up to the cut.

    The history opens with the source agent's own system prompt and initial prompt.
    A tool call whose result was logged after the cut has no result in
    ``source_events``, so it is left out with its result. ``keep_thinking`` set to
    ``False`` leaves out the thinking parts, for a seat whose model did not write them.

    Raises ``ValueError`` when the source agent took no turn before the cut.
    """
    prompts = registered_prompts(
        registration=find_first_registration(events=source_events, agent_id=source_agent_id)
    )
    history = build_message_history(
        events=source_events,
        agent_id=source_agent_id,
        system_prompt=prompts.full_system_prompt,
        runner_prompts=prompts.runner_prompts,
        target_timestamp=source_events[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=False,
        channel_visibility={},
        history_floor_round=None,
        filter_below_round=None,
        split_parallel_tool_calls=split_parallel_tool_calls,
    )
    if not history:
        raise ValueError(f"source agent {source_agent_id!r} took no turn before the cut")
    if keep_thinking:
        return history
    return without_thinking(history=history)


def without_thinking(history: list[ModelMessage]) -> list[ModelMessage]:
    """``history`` with every thinking part removed, and any response left empty dropped.

    A provider takes back only the thinking that its own model wrote: an
    Anthropic block's signature or an OpenAI reasoning item. Thinking from another
    model reaches the seat as empty reasoning items.
    """
    kept: list[ModelMessage] = []
    for message in history:
        if not isinstance(message, ModelResponse):
            kept.append(message)
            continue
        parts = [part for part in message.parts if not isinstance(part, ThinkingPart)]
        if parts:
            kept.append(ModelResponse(parts=parts, timestamp=message.timestamp))
    return kept


def build_transferred_history(
    source_history: list[ModelMessage],
    opening_prompt: str,
) -> list[ModelMessage]:
    """The history a seat starts with: ``source_history``, then ``opening_prompt``.

    The trailing ``ModelRequest`` holds ``opening_prompt``; the runner sends it as
    the agent's first request.
    """
    return [*source_history, ModelRequest(parts=[UserPromptPart(content=opening_prompt)])]


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


def _seats_swapped_in_run(events: list[SimulationEvent]) -> frozenset[str]:
    """The seats that an in-run swap gave to another agent, in this run's log."""
    return frozenset(event.agent_id for event in events if isinstance(event, AgentSwappedMidRun))


def _transferred_seats(
    manifest: HistoryTransferManifest, events: list[SimulationEvent]
) -> dict[str, str]:
    """Each seat that still holds its transferred agent, mapped to its history file.

    A seat that an in-run swap gave to another agent is left out: the agent swapped
    in did not start with the transferred history.
    """
    swapped = _seats_swapped_in_run(events=events)
    return {
        seat.agent_id: seat.history_file for seat in manifest.seats if seat.agent_id not in swapped
    }


async def splice_transferred_histories(
    run_dir: Path, events: list[SimulationEvent], state: RewindState
) -> RewindState:
    """Put each transferred seat's saved history in front of its rebuilt turns.

    Returns ``state`` unchanged for a run without a history-transfer manifest.
    """
    manifest = read_history_transfer_manifest(run_dir=run_dir)
    if manifest is None:
        return state
    histories = dict(state.agent_message_histories)
    for agent_id, history_file in _transferred_seats(manifest=manifest, events=events).items():
        transferred = await read_transferred_history(path=run_dir / history_file)
        histories[agent_id] = append_own_turns(
            transferred=transferred,
            own_history=histories.get(agent_id, []),
        )
    return state._replace(agent_message_histories=histories)


async def with_transferred_history(
    run_dir: Path,
    events: list[SimulationEvent],
    agent_id: str,
    own_history: list[ModelMessage],
) -> list[ModelMessage]:
    """``own_history`` with the agent's saved transferred history in front of it.

    ``own_history`` is rebuilt from the run's own log, as the protocol probes and
    the thread export do. It comes back unchanged for an agent that is not a
    transferred seat of the run in ``run_dir``.
    """
    manifest = read_history_transfer_manifest(run_dir=run_dir)
    if manifest is None:
        return own_history
    history_file = _transferred_seats(manifest=manifest, events=events).get(agent_id)
    if history_file is None:
        return own_history
    transferred = await read_transferred_history(path=run_dir / history_file)
    return append_own_turns(transferred=transferred, own_history=own_history)

"""Which of a run's events are copied context, and the history each seeded seat started from.

A fork-at-round, replace-agent or cross-run run copies its source's log up to the
boundary event its manifest names. Every event up to and including that one is
copied. A replaced or imported seat is not shown those events as its own past: it
starts from a seed rebuilt with the same filter its first launch used. An in-run
swap seeds the swapped-in agent the same way at the swap round.

The seeds are rebuilt rather than read from ``resume_context_*.json``, because a
crashed derived run that is resumed again overwrites that file with the later
resume's history.
"""

from pathlib import Path
from typing import NamedTuple

from pydantic_ai.messages import ModelMessage

from glossogen.message_history_builder import build_message_history
from glossogen.message_rewind import AgentHistoryFilter, build_rewind_state_at_event
from glossogen.model_catalog import SELF_HOSTED_PROVIDER
from glossogen.models.event import AgentRegistered, AgentSwappedMidRun, SimulationEvent
from glossogen.resume_state_loader import (
    imported_seat_history_filter,
    read_cross_run_manifest_info,
    read_replace_manifest_info,
    replaced_seat_history_filter,
)
from glossogen.runners.communication_protocol import (
    build_full_system_prompt,
    registered_runner_prompts,
)


class CopiedContext(NamedTuple):
    """What a run copied from its source.

    ``copied_event_ids`` holds every event up to and including the manifest's
    boundary. ``seeded_agent_id`` is the replaced or imported seat, ``None`` for a
    fork-at-round or an underived run, and ``boundary_seed`` the history it started
    from after the boundary.
    """

    copied_event_ids: frozenset[str]
    seeded_agent_id: str | None
    boundary_seed: list[ModelMessage]


NO_COPIED_CONTEXT = CopiedContext(
    copied_event_ids=frozenset(),
    seeded_agent_id=None,
    boundary_seed=[],
)


async def load_copied_context(run_dir: Path, events: list[SimulationEvent]) -> CopiedContext:
    """Read the run's manifest and rebuild its seeded seat's history at the boundary."""
    cross_run_info = read_cross_run_manifest_info(run_dir=run_dir)
    if cross_run_info is not None:
        return _copied_context(
            events=events,
            target_event_id=cross_run_info.target_event_id,
            entry_round=cross_run_info.entry_round,
            seeded_agent_id=cross_run_info.replaced_agent_id,
            seat_filter=await imported_seat_history_filter(cross_run_info=cross_run_info),
        )
    replace_info = read_replace_manifest_info(run_dir=run_dir)
    if replace_info is None:
        return NO_COPIED_CONTEXT
    if replace_info.replaced_agent_id is None:
        return CopiedContext(
            copied_event_ids=_ids_through(
                events=events, target_event_id=replace_info.target_event_id
            ),
            seeded_agent_id=None,
            boundary_seed=[],
        )
    return _copied_context(
        events=events,
        target_event_id=replace_info.target_event_id,
        entry_round=replace_info.entry_round,
        seeded_agent_id=replace_info.replaced_agent_id,
        seat_filter=replaced_seat_history_filter(replace_info=replace_info),
    )


def build_swap_seed(
    events: list[SimulationEvent],
    swap: AgentSwappedMidRun,
    registration: AgentRegistered,
) -> list[ModelMessage]:
    """The history an in-run swap seeded the new agent with, as ``execute_agent_swap`` built it."""
    swap_index = next(
        index for index, event in enumerate(events) if event.event_id == swap.event_id
    )
    return build_message_history(
        events=events[:swap_index],
        agent_id=swap.agent_id,
        system_prompt=build_full_system_prompt(
            base_prompt=registration.system_prompt,
            prompts=registered_runner_prompts(registration=registration),
        ),
        runner_prompts=registered_runner_prompts(registration=registration),
        target_timestamp=swap.timestamp,
        cutoff_round=swap.round_number,
        tool_calls_only=True,
        channel_visibility=swap.channel_visibility,
        filter_below_round=None,
        split_parallel_tool_calls=swap.new_provider == SELF_HOSTED_PROVIDER,
    )


def _copied_context(
    events: list[SimulationEvent],
    target_event_id: str,
    entry_round: int,
    seeded_agent_id: str,
    seat_filter: AgentHistoryFilter,
) -> CopiedContext:
    state = build_rewind_state_at_event(
        events=events,
        target_event_id=target_event_id,
        cutoff_round=entry_round,
        agent_filters={seeded_agent_id: seat_filter},
    )
    return CopiedContext(
        copied_event_ids=_ids_through(events=events, target_event_id=target_event_id),
        seeded_agent_id=seeded_agent_id,
        boundary_seed=state.agent_message_histories.get(seeded_agent_id, []),
    )


def _ids_through(events: list[SimulationEvent], target_event_id: str) -> frozenset[str]:
    ids: set[str] = set()
    for event in events:
        ids.add(event.event_id)
        if event.event_id == target_event_id:
            return frozenset(ids)
    raise ValueError(f"Boundary event {target_event_id} is not in the run's log")

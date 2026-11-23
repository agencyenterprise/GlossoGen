"""Seating a new run's agents with the histories agents built in another finished run.

A history-transfer run is a fresh run, of any scenario, in which chosen seats
start with the history an agent built in a source run: that agent's system
prompt, text, thinking, tool calls and tool results up to a round, then one
message that opens the new run with its own system and initial prompts. The
source may be a run of another scenario, so a seat's id and its source agent's
id may differ.

Planning reads and checks the source before the new run claims a directory.
Preparing builds each seat's history once the run's agents exist, saves it, and
writes the manifest that names the source.
"""

import logging
import time
from pathlib import Path
from typing import NamedTuple

from pydantic_ai.messages import ModelMessage

from glossogen.model_catalog.provider_catalog import Provider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import (
    AgentRegistered,
    RoundAdvanced,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
)
from glossogen.run_derivation.replace_agent import (
    collect_source_agents,
    refuse_seat_swapped_before_cutoff,
    refuse_seat_with_mixed_history,
)
from glossogen.run_replay.message_rewind import RoundEndCutoff, resolve_round_end_cutoff
from glossogen.run_replay.transferred_history import (
    build_source_history,
    build_transferred_history,
    write_transferred_history,
)
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.history_transfer_manifest import (
    HistoryTransferManifest,
    TransferredSeat,
    transferred_history_file_name,
    write_history_transfer_manifest,
)
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.run_storage.run_identity import compose_run_id
from glossogen.scenario_contract.platform_runner_prompts import (
    build_full_system_prompt,
    history_transfer_prompt,
    runner_prompts_for,
)
from glossogen.scenario_contract.protocol import SimulationScenario

logger = logging.getLogger(__name__)


class HistoryTransferRequest(NamedTuple):
    """Which source run the histories come from, and which seat carries which agent's.

    ``seat_sources`` maps each seat of the new run to the source agent whose
    history it starts with. ``source_round_end`` is the last source round the
    histories keep; ``None`` keeps every round of a source that finished.
    """

    source_run_dir: Path
    source_scenario_name: str
    seat_sources: dict[str, str]
    source_round_end: int | None


class HistoryTransferPlan(NamedTuple):
    """A checked request, with the source events and the cut the histories are built from."""

    source_run_id: str
    source_run_dir: Path
    source_events: list[SimulationEvent]
    cutoff: RoundEndCutoff
    seat_sources: dict[str, str]
    source_registrations: dict[str, AgentRegistered]


async def plan_history_transfer(
    request: HistoryTransferRequest, seat_ids: list[str]
) -> HistoryTransferPlan:
    """Check ``request`` against the source run and the new run's ``seat_ids``.

    Raises ``ValueError`` for an unknown seat or source agent, a source that has
    not reached the round, a source with no round given that has not finished,
    a source agent whose log does not hold its whole history, and a source agent
    that took no turn by the end of the round.
    """
    if not request.seat_sources:
        raise ValueError("name at least one seat to carry a transferred history")
    unknown_seats = sorted(set(request.seat_sources) - set(seat_ids))
    if unknown_seats:
        raise ValueError(
            f"seats {unknown_seats} are not agents of this run (its agents: {sorted(seat_ids)})"
        )
    log_path = event_log_path(
        run_dir=request.source_run_dir, scenario_name=request.source_scenario_name
    )
    if not log_path.exists():
        raise ValueError(f"source run log not found: {log_path}")
    events = await load_events(log_path=log_path)
    _require_scenario(events=events, scenario_name=request.source_scenario_name)
    round_end = _resolve_source_round_end(
        events=events, requested_round_end=request.source_round_end
    )
    try:
        cutoff = resolve_round_end_cutoff(events=events, round_end=round_end)
    except ValueError as exc:
        raise ValueError(f"source run {request.source_run_dir}: {exc}") from exc
    source_agents = collect_source_agents(events=events, boundary_timestamp=cutoff.timestamp)
    for source_agent_id in sorted(set(request.seat_sources.values())):
        if source_agent_id not in source_agents:
            raise ValueError(
                f"agent {source_agent_id!r} is not in source run {request.source_run_dir} "
                f"by the end of round {round_end} (its agents: {sorted(source_agents)})"
            )
        refuse_seat_with_mixed_history(
            source_run_dir=request.source_run_dir, agent_id=source_agent_id
        )
        refuse_seat_swapped_before_cutoff(
            source_events=events,
            cutoff_timestamp=cutoff.timestamp,
            agent_id=source_agent_id,
        )
        # Built here only to refuse a source agent with no turns before the run
        # claims a directory; prepare rebuilds it for the seat's provider.
        build_source_history(
            source_events=events,
            source_agent_id=source_agent_id,
            cutoff=cutoff,
            split_parallel_tool_calls=False,
        )
    return HistoryTransferPlan(
        source_run_id=compose_run_id(
            scenario_name=request.source_scenario_name,
            run_dir_name=request.source_run_dir.name,
        ),
        source_run_dir=request.source_run_dir,
        source_events=events,
        cutoff=cutoff,
        seat_sources=dict(request.seat_sources),
        source_registrations=source_agents,
    )


def _require_scenario(events: list[SimulationEvent], scenario_name: str) -> None:
    """Raise unless ``events`` open with a ``SimulationStarted`` of ``scenario_name``."""
    if not events or not isinstance(events[0], SimulationStarted):
        raise ValueError("the source run's log does not open with simulation_started")
    if events[0].scenario_name != scenario_name:
        raise ValueError(
            f"the source run is a {events[0].scenario_name!r} run, not {scenario_name!r}"
        )


def _resolve_source_round_end(
    events: list[SimulationEvent], requested_round_end: int | None
) -> int:
    """The requested round, or the last round of a source that finished.

    A source still running, or one that crashed, has no settled last round, so
    the caller must name the round to keep.
    """
    if requested_round_end is not None:
        return requested_round_end
    if not any(isinstance(event, SimulationEnded) for event in events):
        raise ValueError(
            "the source run has not finished (its log has no simulation_ended); "
            "name the last source round to keep"
        )
    rounds = [event.round_number for event in events if isinstance(event, RoundAdvanced)]
    if not rounds:
        raise ValueError("the source run never started a round")
    return max(rounds)


async def prepare_history_transfer(
    plan: HistoryTransferPlan,
    run_dir: Path,
    scenario: SimulationScenario,
    agents: list[AgentConfig],
) -> dict[str, list[ModelMessage]]:
    """Build and save each transferred seat's history and the run's manifest.

    Returns the histories by seat. Each ends with the message that opens the
    run: the seat's full system prompt and initial prompt in this scenario.
    """
    agents_by_id = {agent.agent_id: agent for agent in agents}
    histories: dict[str, list[ModelMessage]] = {}
    seats: list[TransferredSeat] = []
    for seat_id, source_agent_id in sorted(plan.seat_sources.items()):
        agent = agents_by_id[seat_id]
        history = build_transferred_history(
            source_events=plan.source_events,
            source_agent_id=source_agent_id,
            cutoff=plan.cutoff,
            opening_prompt=_opening_prompt(scenario=scenario, agent=agent),
            split_parallel_tool_calls=agent.provider == Provider.SELF_HOSTED,
        )
        history_file = transferred_history_file_name(agent_id=seat_id)
        await write_transferred_history(path=run_dir / history_file, history=history)
        histories[seat_id] = history
        source_registration = plan.source_registrations[source_agent_id]
        seats.append(
            TransferredSeat(
                agent_id=seat_id,
                source_agent_id=source_agent_id,
                source_model=source_registration.model,
                source_provider=source_registration.provider,
                history_file=history_file,
            )
        )
        logger.info(
            "Seat %s carries %s's history from %s (rounds 1-%d, %d messages, source model %s)",
            seat_id,
            source_agent_id,
            plan.source_run_id,
            plan.cutoff.cutoff_round - 1,
            len(history),
            source_registration.model,
        )
    write_history_transfer_manifest(
        run_dir=run_dir,
        manifest=HistoryTransferManifest(
            source_run_id=plan.source_run_id,
            source_run_dir=str(plan.source_run_dir),
            source_round_end=plan.cutoff.cutoff_round - 1,
            seats=seats,
            transferred_at=time.time(),
        ),
    )
    return histories


def _opening_prompt(scenario: SimulationScenario, agent: AgentConfig) -> str:
    """The message that opens the run for ``agent``, rendered as its runner will see it."""
    runner_prompts = runner_prompts_for(
        role_name=agent.role_name,
        replacement=scenario.runner_prompts(agent_id=agent.agent_id),
    )
    return history_transfer_prompt(
        full_system_prompt=build_full_system_prompt(
            base_prompt=agent.system_prompt, prompts=runner_prompts
        ),
        prompts=runner_prompts,
    )

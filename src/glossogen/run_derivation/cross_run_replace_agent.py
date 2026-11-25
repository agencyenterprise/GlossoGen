"""Core implementation of the cross-run replace-agent operation.

Imports one agent, with its full pydantic-ai history (text, thinking,
tool calls), from a different completed run (``Sim B``) into a target
run (``Sim A``) at a chosen round boundary, and resumes the simulation.
The target run's other agents continue with their full Sim A history.

Used by the ``glossogen cross-run-replace-agent`` CLI subcommand. Same
scenario and same ``agent_id`` only.
"""

import logging
import shutil
import time
from pathlib import Path
from typing import Any, NamedTuple

import orjson

from glossogen.model_catalog.provider_catalog import SIMULATION_PROVIDERS
from glossogen.run_derivation.replace_agent import (
    build_fork_run_config,
    clone_source_at_boundary,
    collect_source_agents,
    opening_simulation_started,
    prepared_fork_run,
    refuse_boundary_with_swapped_seats,
    refuse_seat_swapped_before_cutoff,
    refuse_seat_with_mixed_history,
    refuse_unforkable_source,
    resolve_fork_boundary,
    write_fork_run_config,
)
from glossogen.run_derivation.run_launching import PreparedForkRun, launch_prepared_run
from glossogen.run_replay.message_rewind import resolve_round_end_cutoff
from glossogen.run_storage.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    IMPORTED_HISTORY_SOURCE_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.run_archive import find_event_offset
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.run_storage.run_identity import compose_run_id
from glossogen.scenario_contract.loader import get_scenario_class
from glossogen.scenario_contract.protocol import SimulationScenario

logger = logging.getLogger(__name__)


class CrossRunReplaceAgentRequest(NamedTuple):
    """Input parameters for a cross-run replace-agent operation.

    The replacement boundary is the *end* of round ``after_round`` in
    Sim A: the fork keeps that round's verdict and postmortem and plays
    round ``after_round + 1`` onward. The imported agent's pydantic-ai
    history is reconstructed from Sim B up to the end of round
    ``source_b_round_end`` (i.e. up to Sim B's
    ``RoundAdvanced(source_b_round_end + 1)`` event, or Sim B's last
    event when Sim B did not advance further).

    ``model`` / ``provider`` are the concrete model/provider the
    imported agent runs under. The CLI resolves "use Sim B's defaults"
    before constructing this request so the core flow always has explicit
    values.

    ``rounds_after`` is how many new rounds the fork plays: round_count
    is set to ``after_round + rounds_after``. When ``None``, a
    ``round_count`` in ``knobs`` sets the total, and without one it
    defaults to ``source_a_round_count - after_round`` (the target run's
    rounds past the boundary).
    """

    source_a_run_dir: Path
    source_b_run_dir: Path
    scenario_name: str
    after_round: int
    source_b_round_end: int
    rounds_after: int | None
    replaced_agent_id: str
    model: str
    provider: str
    knobs: dict[str, Any] | None
    channels_with_visible_history: list[str]
    runs_dir: Path


class CrossRunReplaceAgentResult(NamedTuple):
    """Result of a successful cross-run replace-agent launch."""

    new_run_id: str
    new_run_dir: Path


def _compute_blocked_tool_call_channels(
    scenario_cls: type[SimulationScenario],
    sim_a_imported_agent_channels: list[str],
    sim_b_imported_agent_channels: list[str],
) -> list[str]:
    """Return sorted blocked channel IDs for the imported agent's history.

    Combines the scenario's default blocked channels (e.g. veyru's
    postmortem) with any channel the imported agent had in Sim B that
    does not exist in Sim A, because those tool calls would reference channel
    IDs the live runtime does not recognize.
    """
    scenario_blocked = scenario_cls.get_replace_agent_blocked_tool_call_channels()
    sim_a_set = set(sim_a_imported_agent_channels)
    sim_b_only = [ch for ch in sim_b_imported_agent_channels if ch not in sim_a_set]
    combined = set(scenario_blocked) | set(sim_b_only)
    return sorted(combined)


async def prepare_cross_run_replace_agent_run(
    request: CrossRunReplaceAgentRequest,
) -> PreparedForkRun:
    """Prepare a cross-run replace-agent run on disk, without launching it.

    Raises ``ValueError`` for caller-fixable errors (unknown provider /
    scenario / agent / mismatched scenarios) so the CLI layer can surface
    a clear message without re-implementing validation.
    """
    # Raises with the loaded scenario names before any file is touched.
    get_scenario_class(name=request.scenario_name)
    if request.provider not in SIMULATION_PROVIDERS:
        raise ValueError(f"Unknown provider: {request.provider}")

    refuse_unforkable_source(
        source_run_dir=request.source_a_run_dir,
        replaced_agent_id=request.replaced_agent_id,
    )
    refuse_seat_with_mixed_history(
        source_run_dir=request.source_b_run_dir,
        agent_id=request.replaced_agent_id,
    )

    source_a_log_path = event_log_path(
        run_dir=request.source_a_run_dir, scenario_name=request.scenario_name
    )
    if not source_a_log_path.exists():
        raise ValueError(f"Source A run JSONL not found: {source_a_log_path}")
    source_b_log_path = event_log_path(
        run_dir=request.source_b_run_dir, scenario_name=request.scenario_name
    )
    if not source_b_log_path.exists():
        raise ValueError(f"Source B run JSONL not found: {source_b_log_path}")

    source_a_events = await load_events(log_path=source_a_log_path)
    source_b_events = await load_events(log_path=source_b_log_path)

    source_a_first_event = opening_simulation_started(events=source_a_events, run_label="source A")
    source_b_first_event = opening_simulation_started(events=source_b_events, run_label="source B")
    if source_a_first_event.scenario_name != source_b_first_event.scenario_name:
        raise ValueError(
            f"Scenario mismatch: source A is {source_a_first_event.scenario_name!r}, "
            f"source B is {source_b_first_event.scenario_name!r}"
        )
    if source_a_first_event.scenario_name != request.scenario_name:
        raise ValueError(
            f"Scenario mismatch: request is {request.scenario_name!r}, "
            f"source runs are {source_a_first_event.scenario_name!r}"
        )

    boundary = resolve_fork_boundary(
        events=source_a_events,
        after_round=request.after_round,
    )
    target_event_id = boundary.target_event_id
    entry_round = request.after_round + 1
    try:
        source_b_cutoff = resolve_round_end_cutoff(
            events=source_b_events, round_end=request.source_b_round_end
        )
    except ValueError as exc:
        raise ValueError(f"Source B: {exc}") from exc
    source_b_cutoff_event_id = source_b_cutoff.event_id
    source_a_boundary_timestamp = boundary.boundary_timestamp
    source_b_boundary_timestamp = source_b_cutoff.timestamp
    refuse_boundary_with_swapped_seats(
        events=source_a_events,
        boundary_timestamp=source_a_boundary_timestamp,
        replaced_agent_id=request.replaced_agent_id,
    )
    refuse_seat_swapped_before_cutoff(
        source_events=source_b_events,
        cutoff_timestamp=source_b_boundary_timestamp,
        agent_id=request.replaced_agent_id,
    )
    source_a_agents = collect_source_agents(
        events=source_a_events,
        boundary_timestamp=source_a_boundary_timestamp,
    )
    source_b_agents = collect_source_agents(
        events=source_b_events,
        boundary_timestamp=source_b_boundary_timestamp,
    )
    if request.replaced_agent_id not in source_a_agents:
        raise ValueError(
            f"Agent {request.replaced_agent_id!r} not found in source A run "
            f"as of the end of round {request.after_round} "
            f"(known agents: {sorted(source_a_agents)})"
        )
    if request.replaced_agent_id not in source_b_agents:
        raise ValueError(
            f"Agent {request.replaced_agent_id!r} not found in source B run "
            f"as of round {request.source_b_round_end} "
            f"(known agents: {sorted(source_b_agents)})"
        )

    location = await find_event_offset(
        log_path=source_a_log_path,
        event_id=target_event_id,
    )
    if location is None:
        raise ValueError(
            f"No event {target_event_id} "
            f"(fork boundary after round {request.after_round}) "
            f"found in {source_a_log_path}"
        )

    scenario_cls = get_scenario_class(name=request.scenario_name)

    sim_a_imported_registration = source_a_agents[request.replaced_agent_id]

    fork_config = build_fork_run_config(
        scenario_cls=scenario_cls,
        source_scenario_config=source_a_first_event.scenario_config,
        knobs=request.knobs,
        after_round=request.after_round,
        rounds_after=request.rounds_after,
        source_agents=source_a_agents,
        replaced_agent_id=request.replaced_agent_id,
        replacement_model=request.model,
        replacement_provider=request.provider,
        default_model=request.model,
        default_provider=request.provider,
    )

    cloned = await clone_source_at_boundary(
        source_run_dir=request.source_a_run_dir,
        runs_dir=request.runs_dir,
        scenario_name=request.scenario_name,
        truncate_after_offset=location.end_offset,
    )

    imported_history_path = cloned.new_run_dir / IMPORTED_HISTORY_SOURCE_FILENAME
    shutil.copyfile(src=source_b_log_path, dst=imported_history_path)

    config_path = write_fork_run_config(cloned=cloned, scenario_config=fork_config.scenario_config)

    blocked_tool_call_channels = _compute_blocked_tool_call_channels(
        scenario_cls=scenario_cls,
        sim_a_imported_agent_channels=list(sim_a_imported_registration.channel_ids),
        sim_b_imported_agent_channels=list(source_b_agents[request.replaced_agent_id].channel_ids),
    )

    source_a_run_id = compose_run_id(
        scenario_name=request.scenario_name,
        run_dir_name=request.source_a_run_dir.name,
    )
    source_b_run_id = compose_run_id(
        scenario_name=request.scenario_name,
        run_dir_name=request.source_b_run_dir.name,
    )
    manifest = CrossRunReplaceManifest(
        source_a_run_id=source_a_run_id,
        source_a_run_dir=str(request.source_a_run_dir),
        source_b_run_id=source_b_run_id,
        source_b_run_dir=str(request.source_b_run_dir),
        imported_history_source=IMPORTED_HISTORY_SOURCE_FILENAME,
        round_start=entry_round,
        rounds_after_swap=fork_config.rounds_after_swap,
        target_event_id=target_event_id,
        source_b_round_end=request.source_b_round_end,
        source_b_cutoff_event_id=source_b_cutoff_event_id,
        replaced_agent_id=request.replaced_agent_id,
        imported_model=request.model,
        imported_provider=request.provider,
        channels_with_visible_history=list(request.channels_with_visible_history),
        blocked_tool_call_channels=blocked_tool_call_channels,
        replaced_at=time.time(),
    )
    manifest_path = cloned.new_run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME
    manifest_path.write_bytes(orjson.dumps(manifest.model_dump()))

    return prepared_fork_run(
        cloned=cloned,
        scenario_name=request.scenario_name,
        model=request.model,
        provider=request.provider,
        config_path=config_path,
    )


async def cross_run_replace_agent_in_run(
    request: CrossRunReplaceAgentRequest,
) -> CrossRunReplaceAgentResult:
    """Prepare and launch a cross-run replace-agent run.

    The resumed subprocess is spawned detached as a side-effect; see
    :func:`prepare_cross_run_replace_agent_run` for everything before the
    launch.
    """
    prepared = await prepare_cross_run_replace_agent_run(request=request)
    logger.info("Launching cross-run replace-agent simulation: %s", " ".join(prepared.launch_cmd))
    launch_prepared_run(prepared=prepared)
    return CrossRunReplaceAgentResult(
        new_run_id=prepared.new_run_id, new_run_dir=prepared.new_run_dir
    )

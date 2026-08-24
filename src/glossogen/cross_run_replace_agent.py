"""Core implementation of the cross-run replace-agent operation.

Imports one agent, with its full pydantic-ai history (text, thinking,
tool calls), from a different completed run (``Sim B``) into a target
run (``Sim A``) at a chosen round boundary, and resumes the simulation.
The target run's other agents continue with their full Sim A history.

Used by both the FastAPI endpoint and the
``glossogen cross-run-replace-agent`` CLI subcommand. Same scenario and
same ``agent_id`` only.
"""

import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple, cast

import orjson

from glossogen.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    IMPORTED_HISTORY_SOURCE_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.evaluation.log_reader import load_events
from glossogen.message_rewind import find_event_timestamp
from glossogen.models.event import RoundAdvanced, SimulationEvent, SimulationStarted
from glossogen.provider_credentials import require_reachable_models
from glossogen.replace_agent import (
    build_model_overrides,
    collect_source_agents,
    compose_run_id,
    refuse_source_b_with_mixed_seat,
    refuse_unforkable_source,
    resolve_fork_boundary,
    resolve_knob_round_count,
    resolve_rounds_after,
)
from glossogen.run_archive import claim_run_dir, copy_run_at_event, find_event_offset
from glossogen.run_config_validation import validate_run_config
from glossogen.run_jsonl_rewriter import (
    drop_simulation_ended,
    patch_simulation_started_scenario_config,
    rewrite_run_jsonl,
)
from glossogen.run_launching import PreparedForkRun, launch_prepared_run
from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_protocol import SimulationScenario
from glossogen.token_pricing import list_providers

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
    imported agent runs under. Callers (CLI / API router) resolve "use
    Sim B's defaults" before constructing this request so the core
    flow always has explicit values.

    ``rounds_after`` is how many new rounds the fork plays: round_count
    is set to ``after_round + rounds_after``. When ``None``, it defaults
    to ``source_a_round_count - after_round`` (the target run's rounds
    past the boundary).
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


def _resolve_source_b_cutoff_event_id(
    source_b_events: list[SimulationEvent],
    source_b_round_end: int,
) -> str:
    """Locate Sim B's ``RoundAdvanced(source_b_round_end + 1)`` event id.

    Returns the event_id of that ``RoundAdvanced`` when present, or the
    empty string when Sim B never advanced past ``source_b_round_end``
    (in which case the resume code path falls back to Sim B's last
    event timestamp). ``imported_cutoff_round`` is always
    ``source_b_round_end + 1`` regardless.

    Raises ``ValueError`` if Sim B did not even reach ``source_b_round_end``.
    """
    max_round = 0
    cutoff_event_id = ""
    for event in source_b_events:
        if isinstance(event, RoundAdvanced):
            if event.round_number > max_round:
                max_round = event.round_number
            if event.round_number == source_b_round_end + 1 and not cutoff_event_id:
                cutoff_event_id = event.event_id
    if max_round < source_b_round_end:
        raise ValueError(
            f"Source B did not reach round {source_b_round_end} "
            f"(max observed round: {max_round})"
        )
    return cutoff_event_id


def _compute_blocked_tool_call_channels(
    scenario_cls: type[SimulationScenario],
    sim_a_imported_agent_channels: list[str],
    sim_b_imported_agent_channels: list[str],
) -> list[str]:
    """Return sorted blocked channel IDs for the imported agent's history.

    Combines the scenario's default blocked channels (e.g. veyru's
    postmortem) with any channel the imported agent had in Sim B that
    does not exist in Sim A, because those tool calls would reference channel
    IDs the live MCP server does not recognize.
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
    # Raises with the installed scenario names before any file is touched.
    get_scenario_class(name=request.scenario_name)
    if request.provider not in list_providers():
        raise ValueError(f"Unknown provider: {request.provider}")

    refuse_unforkable_source(
        source_run_dir=request.source_a_run_dir,
        replaced_agent_id=request.replaced_agent_id,
    )
    refuse_source_b_with_mixed_seat(
        source_b_run_dir=request.source_b_run_dir,
        imported_agent_id=request.replaced_agent_id,
    )

    source_a_log_path = request.source_a_run_dir / f"{request.scenario_name}.jsonl"
    if not source_a_log_path.exists():
        raise ValueError(f"Source A run JSONL not found: {source_a_log_path}")
    source_b_log_path = request.source_b_run_dir / f"{request.scenario_name}.jsonl"
    if not source_b_log_path.exists():
        raise ValueError(f"Source B run JSONL not found: {source_b_log_path}")

    source_a_events = await load_events(log_path=source_a_log_path)
    source_b_events = await load_events(log_path=source_b_log_path)

    source_a_first_event = source_a_events[0]
    if not isinstance(source_a_first_event, SimulationStarted):
        raise ValueError("First event in source A JSONL is not SimulationStarted")
    source_b_first_event = source_b_events[0]
    if not isinstance(source_b_first_event, SimulationStarted):
        raise ValueError("First event in source B JSONL is not SimulationStarted")
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

    if request.source_b_round_end < 1:
        raise ValueError(f"source_b_round_end must be >= 1 (got {request.source_b_round_end})")

    boundary = resolve_fork_boundary(
        events=source_a_events,
        after_round=request.after_round,
    )
    target_event_id = boundary.target_event_id
    entry_round = request.after_round + 1
    source_b_cutoff_event_id = _resolve_source_b_cutoff_event_id(
        source_b_events=source_b_events,
        source_b_round_end=request.source_b_round_end,
    )
    source_a_boundary_timestamp = boundary.boundary_timestamp
    if source_b_cutoff_event_id:
        source_b_boundary_timestamp = find_event_timestamp(
            events=source_b_events,
            target_event_id=source_b_cutoff_event_id,
        )
    else:
        source_b_boundary_timestamp = source_b_events[-1].timestamp
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

    merged_scenario_config: dict[str, Any] = dict(source_a_first_event.scenario_config)
    if request.knobs is not None:
        merged_scenario_config.update(request.knobs)
    effective_rounds_after_swap = resolve_rounds_after(
        after_round=request.after_round,
        rounds_after=request.rounds_after,
        knob_round_count=resolve_knob_round_count(knobs=request.knobs),
        source_scenario_config=source_a_first_event.scenario_config,
    )
    merged_scenario_config["round_count"] = entry_round + effective_rounds_after_swap
    # Honour any user-provided model_overrides from the merged knobs; anything
    # the user didn't specify falls back to the source-A-active model.
    raw_user_overrides = merged_scenario_config.get("model_overrides")
    user_overrides: dict[str, dict[str, str]] | None = None
    if isinstance(raw_user_overrides, dict):
        coerced: dict[str, dict[str, str]] = {}
        for agent_id, value in cast(dict[Any, Any], raw_user_overrides).items():
            if not isinstance(value, dict) or "model" not in value or "provider" not in value:
                raise ValueError(
                    f"model_overrides[{agent_id!r}] must be an object with "
                    "'model' and 'provider' string fields"
                )
            typed_value = cast(dict[str, Any], value)
            coerced[str(agent_id)] = {
                "model": str(typed_value["model"]),
                "provider": str(typed_value["provider"]),
            }
        user_overrides = coerced
    merged_scenario_config["model_overrides"] = build_model_overrides(
        source_agents=source_a_agents,
        replaced_agent_id=request.replaced_agent_id,
        replacement_model=request.model,
        replacement_provider=request.provider,
        user_overrides=user_overrides,
    )

    validated = validate_run_config(
        scenario_cls=scenario_cls,
        scenario_config=merged_scenario_config,
        default_provider=request.provider,
        valid_providers=set(list_providers()),
    )

    require_reachable_models(
        scenario_cls=scenario_cls,
        scenario_config=validated.scenario_config,
        agent_overrides=validated.normalized_agent_overrides,
        default_model=request.model,
        default_provider=request.provider,
        first_round=entry_round,
    )

    new_run_dir = claim_run_dir(
        runs_dir=request.runs_dir,
        scenario_name=request.scenario_name,
    )
    new_log_filename = f"{request.scenario_name}.jsonl"
    await copy_run_at_event(
        source_dir=request.source_a_run_dir,
        target_dir=new_run_dir,
        jsonl_path_within_run=Path(new_log_filename),
        truncate_after_offset=location.end_offset,
    )

    new_run_id = compose_run_id(
        scenario_name=request.scenario_name,
        run_dir_name=new_run_dir.name,
    )
    new_log_path = new_run_dir / new_log_filename

    rewrite_run_jsonl(
        log_path=new_log_path,
        new_run_id=new_run_id,
        message_edits={},
        should_drop_event=drop_simulation_ended,
    )

    imported_history_path = new_run_dir / IMPORTED_HISTORY_SOURCE_FILENAME
    shutil.copyfile(src=source_b_log_path, dst=imported_history_path)

    config_path = new_run_dir / "replace_config.json"
    config_path.write_bytes(orjson.dumps(validated.scenario_config))

    patch_simulation_started_scenario_config(
        log_path=new_log_path,
        scenario_config=validated.scenario_config,
    )

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
        rounds_after_swap=effective_rounds_after_swap,
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
    manifest_path = new_run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME
    manifest_path.write_bytes(orjson.dumps(manifest.model_dump()))

    stdout_log = new_run_dir / f"{request.scenario_name}_stdout.log"
    cmd = (
        sys.executable,
        "-m",
        "glossogen",
        "run",
        request.scenario_name,
        "--model",
        request.model,
        "--provider",
        request.provider,
        "--resume",
        str(new_run_dir),
        "--config",
        str(config_path),
    )
    return PreparedForkRun(
        new_run_id=new_run_id,
        new_run_dir=new_run_dir,
        launch_cmd=cmd,
        stdout_log_path=stdout_log,
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

"""Core implementation of the cross-run replace-agent operation.

Imports one agent — with its full pydantic-ai history (text, thinking,
tool calls) — from a different completed run (``Sim B``) into a target
run (``Sim A``) at a chosen round boundary, and resumes the simulation.
The target run's other agents continue with their full Sim A history.

Used by both the FastAPI endpoint and the
``schmidt cross-run-replace-agent`` CLI subcommand. Same scenario and
same ``agent_id`` only.
"""

import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple

import orjson

from schmidt.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    IMPORTED_HISTORY_SOURCE_FILENAME,
    CrossRunReplaceManifest,
)
from schmidt.evaluation.log_reader import load_events
from schmidt.models.event import RoundAdvanced, SimulationEvent, SimulationStarted
from schmidt.replace_agent import (
    _build_model_overrides,
    _collect_source_agents,
    compose_run_id,
    find_round_start_timestamp,
    resolve_round_start_anchor,
)
from schmidt.run_config_validation import validate_run_config
from schmidt.run_jsonl_rewriter import patch_simulation_started_scenario_config, rewrite_run_jsonl
from schmidt.run_repository import RunRepository, claim_run_dir
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenario_registry import SCENARIO_REGISTRY
from schmidt.token_pricing import list_providers

logger = logging.getLogger(__name__)


class CrossRunReplaceAgentRequest(NamedTuple):
    """Input parameters for a cross-run replace-agent operation.

    The replacement boundary is the *start* of round ``round_start`` in
    Sim A. The imported agent's pydantic-ai history is reconstructed
    from Sim B up to the end of round ``source_b_round_end`` (i.e. up to
    Sim B's ``RoundAdvanced(source_b_round_end + 1)`` event, or Sim B's
    last event when Sim B did not advance further).

    ``model`` / ``provider`` are the concrete model/provider the
    imported agent runs under. Callers (CLI / API router) resolve "use
    Sim B's defaults" before constructing this request so the core
    flow always has explicit values.

    ``rounds_after_swap`` controls how many rounds the resumed
    simulation will play following the replacement: round_count is set
    to ``round_start + rounds_after_swap``. When ``None``, defaults to
    ``source_a_round_count - round_start`` (the remaining rounds in the
    target run after the replacement boundary).
    """

    source_a_run_dir: Path
    source_b_run_dir: Path
    scenario_name: str
    round_start: int
    source_b_round_end: int
    rounds_after_swap: int | None
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
    does not exist in Sim A — those tool calls would reference channel
    IDs the live MCP server does not recognize.
    """
    scenario_blocked = scenario_cls.get_replace_agent_blocked_tool_call_channels()
    sim_a_set = set(sim_a_imported_agent_channels)
    sim_b_only = [ch for ch in sim_b_imported_agent_channels if ch not in sim_a_set]
    combined = set(scenario_blocked) | set(sim_b_only)
    return sorted(combined)


def _launch_subprocess(cmd: list[str], log_file: Any) -> None:
    """Launch the resumed simulation in the background."""
    subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


async def cross_run_replace_agent_in_run(
    request: CrossRunReplaceAgentRequest,
) -> CrossRunReplaceAgentResult:
    """Run the full cross-run replace-agent operation and launch the resumed subprocess.

    Raises ``ValueError`` for caller-fixable errors (unknown provider /
    scenario / agent / mismatched scenarios) so the API and CLI layers
    can surface a clear message without re-implementing validation.
    """
    if request.scenario_name not in SCENARIO_REGISTRY:
        raise ValueError(f"Unknown scenario: {request.scenario_name}")
    if request.provider not in list_providers():
        raise ValueError(f"Unknown provider: {request.provider}")

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

    target_event_id = resolve_round_start_anchor(
        events=source_a_events,
        round_start=request.round_start,
    )
    source_b_cutoff_event_id = _resolve_source_b_cutoff_event_id(
        source_b_events=source_b_events,
        source_b_round_end=request.source_b_round_end,
    )
    source_a_boundary_timestamp = find_round_start_timestamp(
        events=source_a_events,
        target_event_id=target_event_id,
    )
    if source_b_cutoff_event_id:
        source_b_boundary_timestamp = find_round_start_timestamp(
            events=source_b_events,
            target_event_id=source_b_cutoff_event_id,
        )
    else:
        source_b_boundary_timestamp = source_b_events[-1].timestamp
    source_a_agents = _collect_source_agents(
        events=source_a_events,
        boundary_timestamp=source_a_boundary_timestamp,
    )
    source_b_agents = _collect_source_agents(
        events=source_b_events,
        boundary_timestamp=source_b_boundary_timestamp,
    )
    if request.replaced_agent_id not in source_a_agents:
        raise ValueError(
            f"Agent {request.replaced_agent_id!r} not found in source A run "
            f"as of round {request.round_start} (known agents: {sorted(source_a_agents)})"
        )
    if request.replaced_agent_id not in source_b_agents:
        raise ValueError(
            f"Agent {request.replaced_agent_id!r} not found in source B run "
            f"as of round {request.source_b_round_end} "
            f"(known agents: {sorted(source_b_agents)})"
        )

    source_a_repo = RunRepository(run_dir=request.source_a_run_dir)
    target_sha = await source_a_repo.find_commit_for_event_id(
        event_id=target_event_id,
    )
    if target_sha is None:
        raise ValueError(
            f"No git commit found for event {target_event_id} "
            f"(round_advanced for round {request.round_start}) "
            f"in {request.source_a_run_dir}"
        )

    new_run_dir = claim_run_dir(
        runs_dir=request.runs_dir,
        scenario_name=request.scenario_name,
    )
    new_repo = await source_a_repo.clone_to(target_dir=new_run_dir)
    await new_repo.checkout(sha=target_sha)

    new_run_id = compose_run_id(
        scenario_name=request.scenario_name,
        run_dir_name=new_run_dir.name,
    )
    new_log_path = new_run_dir / f"{request.scenario_name}.jsonl"

    rewrite_run_jsonl(
        log_path=new_log_path,
        new_run_id=new_run_id,
        message_edits={},
        should_drop_event=lambda _event_dict: False,
    )

    imported_history_path = new_run_dir / IMPORTED_HISTORY_SOURCE_FILENAME
    shutil.copyfile(src=source_b_log_path, dst=imported_history_path)

    scenario_cls = SCENARIO_REGISTRY[request.scenario_name]

    sim_a_imported_registration = source_a_agents[request.replaced_agent_id]

    merged_scenario_config: dict[str, Any] = dict(source_a_first_event.scenario_config)
    if request.knobs is not None:
        merged_scenario_config.update(request.knobs)
    if request.rounds_after_swap is None:
        source_round_count = source_a_first_event.scenario_config.get("round_count")
        if not isinstance(source_round_count, int):
            raise ValueError(
                "Cannot derive default rounds_after_swap: source A run's "
                "scenario_config has no integer 'round_count' entry"
            )
        effective_rounds_after_swap = source_round_count - request.round_start
        if effective_rounds_after_swap < 0:
            raise ValueError(
                f"round_start ({request.round_start}) exceeds source A run's "
                f"round_count ({source_round_count}); cannot derive default "
                f"rounds_after_swap"
            )
    else:
        effective_rounds_after_swap = request.rounds_after_swap
    merged_scenario_config["round_count"] = request.round_start + effective_rounds_after_swap
    # Honour any user-provided model_overrides from the merged knobs; anything
    # the user didn't specify falls back to the source-A-active model.
    raw_user_overrides = merged_scenario_config.get("model_overrides")
    user_overrides: dict[str, dict[str, str]] | None = None
    if isinstance(raw_user_overrides, dict):
        coerced: dict[str, dict[str, str]] = {}
        for agent_id, value in raw_user_overrides.items():
            if not isinstance(value, dict) or "model" not in value or "provider" not in value:
                raise ValueError(
                    f"model_overrides[{agent_id!r}] must be an object with "
                    "'model' and 'provider' string fields"
                )
            coerced[str(agent_id)] = {
                "model": str(value["model"]),
                "provider": str(value["provider"]),
            }
        user_overrides = coerced
    merged_scenario_config["model_overrides"] = _build_model_overrides(
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
        round_start=request.round_start,
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

    await new_repo.commit(
        message=(
            f"cross-run replace: agent {request.replaced_agent_id} from "
            f"{source_b_run_id} → {request.model}/{request.provider}"
        ),
        paths=None,
    )

    stdout_log = new_run_dir / f"{request.scenario_name}_stdout.log"
    cmd = [
        sys.executable,
        "-m",
        "schmidt",
        "run",
        request.scenario_name,
        "--model",
        request.model,
        "--provider",
        request.provider,
        "--resume",
        str(new_run_dir),
        "--runs-dir",
        str(request.runs_dir),
        "--config",
        str(config_path),
    ]

    logger.info("Launching cross-run replace-agent simulation: %s", " ".join(cmd))

    with open(stdout_log, "w", encoding="utf-8") as log_file:
        _launch_subprocess(cmd=cmd, log_file=log_file)

    return CrossRunReplaceAgentResult(new_run_id=new_run_id, new_run_dir=new_run_dir)

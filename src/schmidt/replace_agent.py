"""Core implementation of the replace-agent and round-anchored resume operations.

Used by both the FastAPI endpoints and the ``schmidt replace-agent`` /
``schmidt resume-at-round`` CLI subcommands. Clones a source run's git
repo at a chosen ``RoundAdvanced`` commit, writes a manifest, commits,
and launches a resumed subprocess.

When ``replaced_agent_id`` is set, that agent restarts fresh while every
other agent keeps its full reconstructed history. When ``replaced_agent_id``
is ``None`` (round-anchored resume), every agent keeps its full reconstructed
history; only the JSONL clone, knob merge, and round-count adjustment happen.
"""

import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple, cast

import orjson

from schmidt.evaluation.log_reader import load_events
from schmidt.message_rewind import build_rewind_state_at_event
from schmidt.models.event import AgentRegistered, RoundAdvanced, SimulationEvent, SimulationStarted
from schmidt.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from schmidt.run_archive import claim_run_dir, copy_run_at_event, find_event_offset
from schmidt.run_config_validation import validate_run_config
from schmidt.run_jsonl_rewriter import patch_simulation_started_scenario_config, rewrite_run_jsonl
from schmidt.scenario_registry import SCENARIO_REGISTRY
from schmidt.token_pricing import list_providers

logger = logging.getLogger(__name__)


class ReplaceAgentRequest(NamedTuple):
    """Input parameters for a replace-agent or round-anchored resume operation.

    The boundary is the *start* of round ``round_start``: the resumed
    simulation enters that round. The exact ``RoundAdvanced`` event that
    anchors the git rewind is resolved internally.

    ``rounds_after_swap`` controls how many rounds the resumed
    simulation will play following the boundary: round_count is set
    to ``round_start + rounds_after_swap``. When ``None``, defaults to
    ``source_round_count - round_start`` (the remaining rounds in the
    original run after the boundary).

    When ``replaced_agent_id`` is set, that agent restarts with only the
    prior agent's tool-call history (text and thinking stripped, blocked
    channels dropped) and runs under ``model``/``provider``; every other
    agent keeps its full reconstructed history pinned to its
    source-active model.

    When ``replaced_agent_id`` is ``None``, the operation is a pure
    round-anchored resume: ``model``, ``provider``, and
    ``channels_with_visible_history`` must also be ``None``, every agent
    keeps its full reconstructed history pinned to its source-active
    model, and knob overrides are the only behavioural change.
    """

    source_run_dir: Path
    scenario_name: str
    round_start: int
    rounds_after_swap: int | None
    replaced_agent_id: str | None
    model: str | None
    provider: str | None
    knobs: dict[str, Any] | None
    channels_with_visible_history: list[str] | None
    channel_history_floors: dict[str, int]
    runs_dir: Path


class ReplaceAgentResult(NamedTuple):
    """Result of a successful replace-agent launch."""

    new_run_id: str
    new_run_dir: Path


def compose_run_id(scenario_name: str, run_dir_name: str) -> str:
    """Build the canonical ``<scenario>/<run_dir>`` identifier."""
    return f"{scenario_name}/{run_dir_name}"


def resolve_round_start_anchor(
    events: list[SimulationEvent],
    round_start: int,
) -> str:
    """Resolve the ``event_id`` of the source's ``RoundAdvanced`` for ``round_start``.

    The resumed simulation rewinds to the commit produced by that event,
    which captures the JSONL state where round ``round_start`` has just
    started but its injections have not yet been delivered. The resumed
    game clock then delivers the round-``round_start`` injections fresh
    on resume.

    Cannot be used for round 1: a clean replacement requires the source
    to have completed round 0 (i.e. there must be a prior round to swap
    out from), which never exists. Cannot be used when the source did
    not reach ``round_start``.

    Raises ``ValueError`` for those cases.
    """
    if round_start <= 1:
        raise ValueError("Cannot replace agent at start of round 1: no prior round to rewind to")
    for event in events:
        if isinstance(event, RoundAdvanced) and event.round_number == round_start:
            return event.event_id
    raise ValueError(
        f"No RoundAdvanced event for round {round_start} in source run; "
        f"the source did not reach that round"
    )


def find_round_start_timestamp(
    events: list[SimulationEvent],
    target_event_id: str,
) -> datetime:
    """Return the timestamp of the ``RoundAdvanced`` event with ``target_event_id``.

    Used to recover the resume-boundary timestamp once
    :func:`resolve_round_start_anchor` has returned its event id, so
    downstream helpers can filter events that occurred at or before that
    boundary in the source timeline.
    """
    for event in events:
        if isinstance(event, RoundAdvanced) and event.event_id == target_event_id:
            return event.timestamp
    raise ValueError(f"No RoundAdvanced event with event_id={target_event_id!r} in source run")


def collect_source_agents(
    events: list[SimulationEvent],
    boundary_timestamp: datetime,
) -> dict[str, AgentRegistered]:
    """Return each agent's latest ``AgentRegistered`` at the resume boundary.

    Filters to events whose timestamp is at or before
    ``boundary_timestamp`` so resuming a multi-swap source picks up each
    agent's model/system_prompt as it was at the chosen boundary — not
    a later in-run swap registration that overwrote it.
    """
    out: dict[str, AgentRegistered] = {}
    for event in events:
        if event.timestamp > boundary_timestamp:
            break
        if isinstance(event, AgentRegistered):
            out[event.agent_id] = event
    return out


def build_model_overrides(
    source_agents: dict[str, AgentRegistered],
    replaced_agent_id: str | None,
    replacement_model: str | None,
    replacement_provider: str | None,
    user_overrides: dict[str, dict[str, str]] | None,
) -> dict[str, dict[str, str]]:
    """Pin every source agent to its source-active model, with user overrides on top.

    Encoding every agent explicitly (rather than relying on the top-level
    ``--model``/``--provider`` defaults) keeps non-replaced agents on
    their exact source-active models. Layering ``user_overrides`` on top
    lets the resume caller pin specific agents to a different model (e.g.
    haiku for cheap smoke tests) without losing the source-pin for the
    remaining agents. When ``replaced_agent_id`` is set, the agent's entry
    is forced to ``replacement_model``/``replacement_provider`` last so
    the replacement payload always wins over the user-provided knob entry.
    """
    overrides: dict[str, dict[str, str]] = {}
    for agent_id, registration in source_agents.items():
        overrides[agent_id] = {
            "model": registration.model,
            "provider": registration.provider,
        }
    if user_overrides is not None:
        for agent_id, override in user_overrides.items():
            if agent_id not in overrides:
                # Pre-validation happens later; reject unknown agent IDs early
                # so the user gets a clear error rather than a silently ignored entry.
                raise ValueError(
                    f"model_overrides references unknown agent_id={agent_id!r}; "
                    f"known agents in source: {sorted(overrides)}"
                )
            overrides[agent_id] = {
                "model": override["model"],
                "provider": override["provider"],
            }
    if replaced_agent_id is not None:
        if replacement_model is None or replacement_provider is None:
            raise ValueError(
                "replacement_model and replacement_provider are required when "
                "replaced_agent_id is set"
            )
        overrides[replaced_agent_id] = {
            "model": replacement_model,
            "provider": replacement_provider,
        }
    return overrides


def _launch_subprocess(cmd: list[str], log_file: Any) -> None:
    """Launch the resumed simulation in the background."""
    subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _validate_replacement_payload(request: ReplaceAgentRequest) -> None:
    """Enforce the request's ``replaced_agent_id`` invariant before any I/O.

    When ``replaced_agent_id`` is set, ``model``, ``provider``, and
    ``channels_with_visible_history`` must all be present and ``provider``
    must be a known provider name. When ``replaced_agent_id`` is ``None``,
    all three companion fields must also be ``None`` and
    ``channel_history_floors`` must be empty so the round-anchored resume
    code path has no half-populated replacement state to interpret.

    Every channel named in ``channel_history_floors`` must also appear in
    ``channels_with_visible_history`` (a windowed channel is still a
    visible channel), and each floor must satisfy ``1 <= floor <= round_start``
    (``floor == round_start`` yields zero prior history — the no-history window).
    """
    if request.replaced_agent_id is None:
        misset = [
            field
            for field, value in (
                ("model", request.model),
                ("provider", request.provider),
                ("channels_with_visible_history", request.channels_with_visible_history),
            )
            if value is not None
        ]
        if request.channel_history_floors:
            misset.append("channel_history_floors")
        if misset:
            raise ValueError(
                f"replaced_agent_id is None but {', '.join(misset)} is set; "
                "round-anchored resume requires all replacement fields to be None"
            )
        return
    missing = [
        field
        for field, value in (
            ("model", request.model),
            ("provider", request.provider),
            ("channels_with_visible_history", request.channels_with_visible_history),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            f"replaced_agent_id is set but {', '.join(missing)} is missing; "
            "replace-agent requires all replacement fields to be provided"
        )
    if request.provider not in list_providers():
        raise ValueError(f"Unknown provider: {request.provider}")
    visible = set(request.channels_with_visible_history or [])
    for channel_id, floor in request.channel_history_floors.items():
        if channel_id not in visible:
            raise ValueError(
                f"channel_history_floors names channel {channel_id!r} which is not in "
                f"channels_with_visible_history; a windowed channel must also be visible"
            )
        if not 1 <= floor <= request.round_start:
            raise ValueError(
                f"channel_history_floors[{channel_id!r}]={floor} must satisfy "
                f"1 <= floor <= round_start ({request.round_start})"
            )


def _pick_subprocess_default_model(
    request: ReplaceAgentRequest,
    source_agents: dict[str, AgentRegistered],
) -> tuple[str, str]:
    """Return the ``--model`` / ``--provider`` pair to launch the resumed subprocess with.

    For replace-agent runs we forward the caller's replacement model so
    the subprocess's ``run`` defaults match the replacement. For
    round-anchored resume runs no agent uses the defaults (every agent
    is pinned via ``model_overrides``) but ``schmidt run`` still requires
    the flags; we pick the first source agent's registration arbitrarily.
    """
    if request.model is not None and request.provider is not None:
        return request.model, request.provider
    first_registration = next(iter(source_agents.values()), None)
    if first_registration is None:
        raise ValueError("Source run has no AgentRegistered events; cannot pick default model")
    return first_registration.model, first_registration.provider


async def replace_agent_in_run(request: ReplaceAgentRequest) -> ReplaceAgentResult:
    """Run the full replace-agent or round-anchored resume operation.

    Launches the resumed subprocess as a side-effect. Raises ``ValueError``
    for caller-fixable errors (unknown provider / scenario / agent /
    inconsistent ``replaced_agent_id`` payload) so the API and CLI layers
    can surface a clear message without re-implementing validation.
    """
    _validate_replacement_payload(request=request)
    if request.scenario_name not in SCENARIO_REGISTRY:
        raise ValueError(f"Unknown scenario: {request.scenario_name}")

    source_log_path = request.source_run_dir / f"{request.scenario_name}.jsonl"
    if not source_log_path.exists():
        raise ValueError(f"Source run JSONL not found: {source_log_path}")

    source_events = await load_events(log_path=source_log_path)

    target_event_id = resolve_round_start_anchor(
        events=source_events,
        round_start=request.round_start,
    )
    boundary_timestamp = find_round_start_timestamp(
        events=source_events,
        target_event_id=target_event_id,
    )
    source_agents = collect_source_agents(
        events=source_events,
        boundary_timestamp=boundary_timestamp,
    )
    if request.replaced_agent_id is not None and request.replaced_agent_id not in source_agents:
        raise ValueError(
            f"Agent {request.replaced_agent_id!r} not found in source run "
            f"as of round {request.round_start} (known agents: {sorted(source_agents)})"
        )

    location = await find_event_offset(
        log_path=source_log_path,
        event_id=target_event_id,
    )
    if location is None:
        raise ValueError(
            f"No event {target_event_id} "
            f"(round_advanced for round {request.round_start}) "
            f"found in {source_log_path}"
        )

    new_run_dir = claim_run_dir(
        runs_dir=request.runs_dir,
        scenario_name=request.scenario_name,
    )
    new_log_filename = f"{request.scenario_name}.jsonl"
    await copy_run_at_event(
        source_dir=request.source_run_dir,
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
        should_drop_event=lambda _event_dict: False,
    )

    rewritten_events = await load_events(log_path=new_log_path)
    build_rewind_state_at_event(
        events=rewritten_events,
        target_event_id=target_event_id,
        cutoff_round=request.round_start,
        agent_filters={},
    )

    source_first_event = source_events[0]
    if not isinstance(source_first_event, SimulationStarted):
        raise ValueError("First event in source JSONL is not SimulationStarted")

    scenario_cls = SCENARIO_REGISTRY[request.scenario_name]

    merged_scenario_config: dict[str, Any] = dict(source_first_event.scenario_config)
    if request.knobs is not None:
        merged_scenario_config.update(request.knobs)
    if request.rounds_after_swap is None:
        source_round_count = source_first_event.scenario_config.get("round_count")
        if not isinstance(source_round_count, int):
            raise ValueError(
                "Cannot derive default rounds_after_swap: source run's "
                "scenario_config has no integer 'round_count' entry"
            )
        effective_rounds_after_swap = source_round_count - request.round_start
        if effective_rounds_after_swap < 0:
            raise ValueError(
                f"round_start ({request.round_start}) exceeds source run's "
                f"round_count ({source_round_count}); cannot derive default "
                f"rounds_after_swap"
            )
    else:
        effective_rounds_after_swap = request.rounds_after_swap
    merged_scenario_config["round_count"] = request.round_start + effective_rounds_after_swap
    # Extract any user-provided model_overrides from the merged knobs so they
    # survive the source-agent pinning that follows. Anything not specified by
    # the user falls back to the source-active model.
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
        source_agents=source_agents,
        replaced_agent_id=request.replaced_agent_id,
        replacement_model=request.model,
        replacement_provider=request.provider,
        user_overrides=user_overrides,
    )

    subprocess_model, subprocess_provider = _pick_subprocess_default_model(
        request=request,
        source_agents=source_agents,
    )
    validated = validate_run_config(
        scenario_cls=scenario_cls,
        scenario_config=merged_scenario_config,
        default_provider=subprocess_provider,
        valid_providers=set(list_providers()),
    )

    config_path = new_run_dir / "replace_config.json"
    config_path.write_bytes(orjson.dumps(validated.scenario_config))

    patch_simulation_started_scenario_config(
        log_path=new_log_path,
        scenario_config=validated.scenario_config,
    )

    source_run_id = compose_run_id(
        scenario_name=request.scenario_name,
        run_dir_name=request.source_run_dir.name,
    )
    if request.replaced_agent_id is None:
        blocked_tool_call_channels: list[str] = []
        visible_channels: list[str] = []
    else:
        blocked_tool_call_channels = sorted(
            scenario_cls.get_replace_agent_blocked_tool_call_channels()
        )
        assert request.channels_with_visible_history is not None
        visible_channels = list(request.channels_with_visible_history)
    manifest = ReplaceManifest(
        source_run_id=source_run_id,
        source_run_dir=str(request.source_run_dir),
        round_start=request.round_start,
        rounds_after_swap=effective_rounds_after_swap,
        target_event_id=target_event_id,
        replaced_agent_id=request.replaced_agent_id,
        replacement_model=request.model,
        replacement_provider=request.provider,
        channels_with_visible_history=visible_channels,
        blocked_tool_call_channels=blocked_tool_call_channels,
        channel_history_floors=dict(request.channel_history_floors),
        replaced_at=time.time(),
    )
    manifest_path = new_run_dir / REPLACE_MANIFEST_FILENAME
    manifest_path.write_bytes(orjson.dumps(manifest.model_dump()))

    stdout_log = new_run_dir / f"{request.scenario_name}_stdout.log"
    cmd = [
        sys.executable,
        "-m",
        "schmidt",
        "run",
        request.scenario_name,
        "--model",
        subprocess_model,
        "--provider",
        subprocess_provider,
        "--resume",
        str(new_run_dir),
        "--runs-dir",
        str(request.runs_dir),
        "--config",
        str(config_path),
    ]

    logger.info("Launching replace-agent simulation: %s", " ".join(cmd))

    with open(stdout_log, "w", encoding="utf-8") as log_file:
        _launch_subprocess(cmd=cmd, log_file=log_file)

    return ReplaceAgentResult(new_run_id=new_run_id, new_run_dir=new_run_dir)

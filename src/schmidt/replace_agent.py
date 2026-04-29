"""Core implementation of the replace-agent operation.

Used by both the FastAPI endpoint and the ``schmidt replace-agent`` CLI
subcommand. Clones a source run's git repo at a chosen message commit,
strips one agent's LLM history events from the JSONL, writes a manifest,
commits, and launches a resumed subprocess in which that agent restarts
fresh while every other agent keeps its full reconstructed history.
"""

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple

import orjson

from schmidt.evaluation.log_reader import load_events
from schmidt.message_rewind import build_rewind_state_at_event
from schmidt.models.event import AgentRegistered, RoundAdvanced, SimulationEvent, SimulationStarted
from schmidt.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from schmidt.run_config_validation import validate_run_config
from schmidt.run_jsonl_rewriter import rewrite_run_jsonl
from schmidt.run_repository import RunRepository, claim_run_dir
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.token_pricing import list_providers

logger = logging.getLogger(__name__)


class ReplaceAgentRequest(NamedTuple):
    """Input parameters for a replace-agent operation.

    The replacement boundary is the *start* of round ``round_start``: the
    resumed simulation enters that round with the chosen agent reusing
    only the prior agent's tool-call history (text and thinking are
    stripped, postmortem tool calls/results are dropped). The exact
    ``MessageSent`` that anchors the git rewind is resolved internally.

    ``rounds_after_swap`` controls how many rounds the resumed
    simulation will play following the replacement: round_count is set
    to ``round_start + rounds_after_swap``, so rounds ``round_start +
    1`` through ``round_start + rounds_after_swap`` play after the
    replacement and the replacement itself enters at ``round_start``.
    When ``None``, defaults to ``source_round_count - round_start``
    (the remaining rounds in the original run after the replacement
    boundary), so a 20-round source run with ``round_start=18`` plays
    2 rounds by default.
    """

    source_run_dir: Path
    scenario_name: str
    round_start: int
    rounds_after_swap: int | None
    replaced_agent_id: str
    model: str
    provider: str
    knobs: dict[str, Any] | None
    channels_with_visible_history: list[str]
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


def _collect_source_agents(events: list[SimulationEvent]) -> dict[str, AgentRegistered]:
    """Return a map of agent_id → its AgentRegistered event from the source run."""
    out: dict[str, AgentRegistered] = {}
    for event in events:
        if isinstance(event, AgentRegistered):
            out[event.agent_id] = event
    return out


def _build_model_overrides(
    source_agents: dict[str, AgentRegistered],
    replaced_agent_id: str,
    replacement_model: str,
    replacement_provider: str,
) -> dict[str, dict[str, str]]:
    """Pin every source agent to its original model, then override the replaced one.

    Encoding every agent explicitly (rather than relying on the top-level
    ``--model``/``--provider`` defaults) keeps non-replaced agents on
    their exact original models.
    """
    overrides: dict[str, dict[str, str]] = {}
    for agent_id, registration in source_agents.items():
        overrides[agent_id] = {
            "model": registration.model,
            "provider": registration.provider,
        }
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


async def replace_agent_in_run(request: ReplaceAgentRequest) -> ReplaceAgentResult:
    """Run the full replace-agent operation and launch the resumed subprocess.

    Raises ``ValueError`` for caller-fixable errors (unknown provider /
    scenario / agent / message ID) so the API and CLI layers can surface
    a clear message without re-implementing validation.
    """
    if request.provider not in list_providers():
        raise ValueError(f"Unknown provider: {request.provider}")
    if request.scenario_name not in SCENARIO_REGISTRY:
        raise ValueError(f"Unknown scenario: {request.scenario_name}")

    source_log_path = request.source_run_dir / f"{request.scenario_name}.jsonl"
    if not source_log_path.exists():
        raise ValueError(f"Source run JSONL not found: {source_log_path}")

    source_events = await load_events(log_path=source_log_path)
    source_agents = _collect_source_agents(events=source_events)
    if request.replaced_agent_id not in source_agents:
        raise ValueError(
            f"Agent {request.replaced_agent_id!r} not found in source run "
            f"(known agents: {sorted(source_agents)})"
        )

    target_event_id = resolve_round_start_anchor(
        events=source_events,
        round_start=request.round_start,
    )

    source_repo = RunRepository(run_dir=request.source_run_dir)
    target_sha = await source_repo.find_commit_for_event_id(
        event_id=target_event_id,
    )
    if target_sha is None:
        raise ValueError(
            f"No git commit found for event {target_event_id} "
            f"(round_advanced for round {request.round_start}) "
            f"in {request.source_run_dir}"
        )

    new_run_dir = claim_run_dir(
        runs_dir=request.runs_dir,
        scenario_name=request.scenario_name,
    )
    new_repo = await source_repo.clone_to(target_dir=new_run_dir)
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

    rewritten_events = await load_events(log_path=new_log_path)
    build_rewind_state_at_event(
        events=rewritten_events,
        target_event_id=target_event_id,
        agent_filters={},
    )

    first_event = rewritten_events[0]
    if not isinstance(first_event, SimulationStarted):
        raise ValueError("First event in rewritten JSONL is not SimulationStarted")

    scenario_cls = SCENARIO_REGISTRY[request.scenario_name]

    merged_scenario_config: dict[str, Any] = dict(first_event.scenario_config)
    if request.knobs is not None:
        merged_scenario_config.update(request.knobs)
    if request.rounds_after_swap is None:
        source_round_count = first_event.scenario_config.get("round_count")
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
    merged_scenario_config["model_overrides"] = _build_model_overrides(
        source_agents=source_agents,
        replaced_agent_id=request.replaced_agent_id,
        replacement_model=request.model,
        replacement_provider=request.provider,
    )

    validated = validate_run_config(
        scenario_cls=scenario_cls,
        scenario_config=merged_scenario_config,
        default_provider=request.provider,
        valid_providers=set(list_providers()),
    )

    config_path = new_run_dir / "replace_config.json"
    config_path.write_bytes(orjson.dumps(validated.scenario_config))

    source_run_id = compose_run_id(
        scenario_name=request.scenario_name,
        run_dir_name=request.source_run_dir.name,
    )
    blocked_tool_call_channels = sorted(scenario_cls.get_replace_agent_blocked_tool_call_channels())
    manifest = ReplaceManifest(
        source_run_id=source_run_id,
        source_run_dir=str(request.source_run_dir),
        round_start=request.round_start,
        rounds_after_swap=effective_rounds_after_swap,
        target_event_id=target_event_id,
        replaced_agent_id=request.replaced_agent_id,
        replacement_model=request.model,
        replacement_provider=request.provider,
        channels_with_visible_history=list(request.channels_with_visible_history),
        blocked_tool_call_channels=blocked_tool_call_channels,
        replaced_at=time.time(),
    )
    manifest_path = new_run_dir / REPLACE_MANIFEST_FILENAME
    manifest_path.write_bytes(orjson.dumps(manifest.model_dump()))

    await new_repo.commit(
        message=(
            f"replace: agent {request.replaced_agent_id} → " f"{request.model}/{request.provider}"
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

    logger.info("Launching replace-agent simulation: %s", " ".join(cmd))

    with open(stdout_log, "w", encoding="utf-8") as log_file:
        _launch_subprocess(cmd=cmd, log_file=log_file)

    return ReplaceAgentResult(new_run_id=new_run_id, new_run_dir=new_run_dir)

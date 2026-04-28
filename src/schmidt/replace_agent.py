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
from pydantic import BaseModel

from schmidt.evaluation.log_reader import load_events
from schmidt.message_rewind import build_rewind_state
from schmidt.models.event import AgentRegistered, MessageSent, SimulationEvent, SimulationStarted
from schmidt.run_config_validation import validate_run_config
from schmidt.run_jsonl_rewriter import rewrite_run_jsonl
from schmidt.run_repository import RunRepository, claim_run_dir
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.token_pricing import list_providers

logger = logging.getLogger(__name__)


REPLACE_MANIFEST_FILENAME = "replace_manifest.json"


class ReplaceManifest(BaseModel):
    """Persisted record of a replace-agent operation.

    Written once at replace-agent time into ``replace_manifest.json`` inside
    the new run directory. The resume code path, evaluators, and inspection
    scripts read it to reconstruct what the replacement saw and which rounds
    were played after the swap.
    """

    source_run_id: str
    source_run_dir: str
    round_start: int
    rounds_after_swap: int
    target_message_id: str
    replaced_agent_id: str
    replacement_model: str
    replacement_provider: str
    channels_with_visible_history: list[str]
    blocked_tool_call_channels: list[str]
    replaced_at: float


def read_replace_manifest(run_dir: Path) -> ReplaceManifest | None:
    """Load ``replace_manifest.json`` from ``run_dir`` or return ``None`` if absent."""
    manifest_path = run_dir / REPLACE_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    return ReplaceManifest.model_validate_json(manifest_path.read_bytes())


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
    """

    source_run_dir: Path
    scenario_name: str
    round_start: int
    rounds_after_swap: int
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


def resolve_round_start_message(
    events: list[SimulationEvent],
    round_start: int,
) -> str:
    """Resolve the message_id we rewind to so round ``round_start`` starts fresh.

    Returns the last ``MessageSent`` whose ``round_number`` is strictly
    less than ``round_start``. The resumed simulation re-enters round
    ``round_start`` with the replaced agent on empty history. Cannot be
    used for round 1: there is no prior message to anchor to.

    Raises ``ValueError`` if ``round_start <= 1`` or no qualifying
    ``MessageSent`` exists.
    """
    if round_start <= 1:
        raise ValueError("Cannot replace agent at start of round 1: no prior message to rewind to")
    candidates = [
        event
        for event in events
        if isinstance(event, MessageSent) and event.round_number < round_start
    ]
    if not candidates:
        raise ValueError(f"No MessageSent event found before round {round_start}")
    return candidates[-1].message.message_id


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

    target_message_id = resolve_round_start_message(
        events=source_events,
        round_start=request.round_start,
    )

    source_repo = RunRepository(run_dir=request.source_run_dir)
    target_sha = await source_repo.find_commit_for_message(
        message_id=target_message_id,
    )
    if target_sha is None:
        raise ValueError(
            f"No git commit found for message {target_message_id} "
            f"(resolved from start of round {request.round_start}) "
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
    build_rewind_state(
        events=rewritten_events,
        target_message_id=target_message_id,
        message_edits={},
        agent_filters={},
    )

    first_event = rewritten_events[0]
    if not isinstance(first_event, SimulationStarted):
        raise ValueError("First event in rewritten JSONL is not SimulationStarted")

    scenario_cls = SCENARIO_REGISTRY[request.scenario_name]

    merged_scenario_config: dict[str, Any] = dict(first_event.scenario_config)
    if request.knobs is not None:
        merged_scenario_config.update(request.knobs)
    merged_scenario_config["round_count"] = request.round_start + request.rounds_after_swap
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
        rounds_after_swap=request.rounds_after_swap,
        target_message_id=target_message_id,
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

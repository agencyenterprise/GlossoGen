"""Scans the runs directory to discover simulation runs and build summaries.

Expects the standard directory layout:
``runs/{scenario_name}/{unix_timestamp}/{scenario_name}.jsonl``
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import aiofiles
import orjson

from schmidt.eval_manifest import read_eval_manifest
from schmidt.event_parsing import parse_event_bytes
from schmidt.models.event import RunStatus, SimulationEnded, SimulationStarted
from schmidt.server.runs.models import AgentModelSummary, ForkSource, ReplaceAgentSource, RunSummary
from schmidt.stream_manifest import delete_manifest, read_manifest
from schmidt.token_pricing import find_pricing

logger = logging.getLogger(__name__)


class _AgentModelInfo(NamedTuple):
    """Raw per-agent model data extracted from JSONL."""

    agent_id: str
    role_name: str
    model: str
    provider: str


class _SinglePassResult(NamedTuple):
    """All data extracted from a single pass over a JSONL file."""

    first_event: SimulationStarted
    last_event: SimulationEnded | None
    unique_models: list[str]
    agent_models: list[AgentModelSummary]
    message_count: int
    cost_usd: float
    current_round: int


async def scan_jsonl(file_path: Path) -> _SinglePassResult:
    """Read a JSONL file once, extracting all data needed for the run summary.

    Collects the first event, the last SimulationEnded (if present in
    the final 20 lines), per-agent model info, message count, and
    token-based cost estimate — all in a single sequential pass.
    """
    first_bytes: bytes | None = None
    tail: list[bytes] = []
    agents_by_id: dict[str, _AgentModelInfo] = {}
    message_count = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    current_round = 0

    async with aiofiles.open(file_path, mode="rb") as f:
        async for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            if first_bytes is None:
                first_bytes = stripped

            tail.append(stripped)
            if len(tail) > 20:
                tail.pop(0)

            raw = orjson.loads(stripped)
            event_type = raw.get("event_type")

            if event_type == "agent_registered":
                agent_id = raw.get("agent_id", "")
                model = raw.get("model", "")
                if agent_id and model:
                    agents_by_id[agent_id] = _AgentModelInfo(
                        agent_id=agent_id,
                        role_name=raw.get("role_name", agent_id),
                        model=model,
                        provider=raw.get("provider", "unknown"),
                    )
            elif event_type == "message_sent":
                message_count += 1
            elif event_type == "llm_response_received":
                usage = raw.get("usage")
                if usage is not None:
                    total_input += usage.get("input_tokens", 0)
                    total_output += usage.get("output_tokens", 0)
                    total_cache_read += usage.get("cache_read_input_tokens", 0)
                    total_cache_write += usage.get("cache_creation_input_tokens", 0)
            elif event_type == "round_advanced":
                round_number = raw.get("round_number", 0)
                if round_number > current_round:
                    current_round = round_number

    if first_bytes is None:
        raise ValueError(f"File is empty: {file_path}")

    first_event = parse_event_bytes(raw_bytes=first_bytes)
    if not isinstance(first_event, SimulationStarted):
        raise ValueError(f"First event is not SimulationStarted in {file_path}")

    last_ended: SimulationEnded | None = None
    for candidate in reversed(tail):
        event = parse_event_bytes(raw_bytes=candidate)
        if isinstance(event, SimulationEnded):
            last_ended = event
            break

    seen: dict[str, None] = {}
    for info in agents_by_id.values():
        if info.model not in seen:
            seen[info.model] = None
    agent_models = [
        AgentModelSummary(
            agent_id=info.agent_id,
            role_name=info.role_name,
            model=info.model,
            provider=info.provider,
        )
        for info in agents_by_id.values()
    ]

    if seen:
        model = list(seen)[0]
    else:
        model = "unknown"
    cost_usd = 0.0
    pricing = find_pricing(model=model)
    if pricing is not None and total_input > 0:
        non_cached_input = max(0, total_input - total_cache_read - total_cache_write)
        cost_usd = (
            non_cached_input * pricing.input_per_mtok
            + total_output * pricing.output_per_mtok
            + total_cache_read * pricing.cache_read_per_mtok
            + total_cache_write * pricing.cache_write_per_mtok
        ) / 1_000_000

    return _SinglePassResult(
        first_event=first_event,
        last_event=last_ended,
        unique_models=list(seen),
        agent_models=agent_models,
        message_count=message_count,
        cost_usd=cost_usd,
        current_round=current_round,
    )


class ResolvedRun(NamedTuple):
    """Lightweight run location returned by resolve_run."""

    run_dir: Path
    scenario_name: str


def compose_run_id(scenario_name: str, run_dir_name: str) -> str:
    """Build the canonical run identifier from its two path components."""
    return f"{scenario_name}/{run_dir_name}"


def resolve_run(runs_dir: Path, scenario_name: str, run_dir_name: str) -> ResolvedRun:
    """Resolve a run directory from its scenario and directory name.

    Raises ValueError if the directory does not exist or contains no JSONL.
    """
    run_dir = runs_dir / scenario_name / run_dir_name
    jsonl_path = run_dir / f"{scenario_name}.jsonl"
    if not run_dir.is_dir() or not jsonl_path.exists():
        raise ValueError(f"Run not found: {compose_run_id(scenario_name, run_dir_name)}")
    return ResolvedRun(run_dir=run_dir, scenario_name=scenario_name)


def _timestamp_from_dir(dir_name: str) -> datetime:
    """Derive a UTC timestamp from a directory name that is a unix epoch.

    Directory names may have a deduplication suffix (e.g. ``1776443092_2``)
    when multiple runs start in the same second. Only the part before the
    first underscore is the actual epoch.
    """
    epoch_str = dir_name.split("_")[0]
    return datetime.fromtimestamp(int(epoch_str), tz=UTC)


def _read_labels(run_dir: Path) -> list[str]:
    """Read labels from labels.json if it exists, returning empty list otherwise."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return []
    try:
        result: list[str] = orjson.loads(labels_path.read_bytes())
        return result
    except Exception:
        logger.exception("Failed to read labels from %s", labels_path)
        return []


def _has_note(run_dir: Path) -> bool:
    """Check whether a note.md file exists in the run directory."""
    return (run_dir / "note.md").exists()


def _read_fork_source(run_dir: Path) -> ForkSource | None:
    """Read fork provenance from fork_manifest.json if it exists."""
    manifest_path = run_dir / "fork_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    forked_at = datetime.fromtimestamp(raw["forked_at"], tz=UTC)
    return ForkSource(
        source_run_id=raw["source_run_id"],
        target_message_id=raw["target_message_id"],
        forked_at=forked_at,
    )


def _read_replace_agent_source(run_dir: Path) -> ReplaceAgentSource | None:
    """Read replace-agent provenance from replace_manifest.json if it exists."""
    manifest_path = run_dir / "replace_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    replaced_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    return ReplaceAgentSource(
        source_run_id=raw["source_run_id"],
        round_start=raw["round_start"],
        target_message_id=raw["target_message_id"],
        replaced_agent_id=raw["replaced_agent_id"],
        replacement_model=raw["replacement_model"],
        replacement_provider=raw["replacement_provider"],
        replaced_at=replaced_at,
    )


async def _build_summary(
    scenario_name: str,
    timestamp_dir: Path,
) -> RunSummary | None:
    """Build a RunSummary for a single run directory.

    Returns None if the directory does not contain a valid run.
    """
    jsonl_path = timestamp_dir / f"{scenario_name}.jsonl"
    if not jsonl_path.exists():
        return None

    try:
        scan = await scan_jsonl(file_path=jsonl_path)
    except Exception:
        logger.exception("Failed to parse run at %s", timestamp_dir)
        return None

    first_event = scan.first_event
    report_path = timestamp_dir / f"{scenario_name}_report.json"
    fork_source = _read_fork_source(run_dir=timestamp_dir)
    replace_agent_source = _read_replace_agent_source(run_dir=timestamp_dir)
    run_timestamp = _timestamp_from_dir(dir_name=timestamp_dir.name)
    labels = _read_labels(run_dir=timestamp_dir)
    has_note = _has_note(run_dir=timestamp_dir)
    eval_in_progress = read_eval_manifest(run_dir=timestamp_dir) is not None

    run_id = compose_run_id(scenario_name=scenario_name, run_dir_name=timestamp_dir.name)

    if scan.last_event is not None:
        derived = fork_source is not None or replace_agent_source is not None
        start_time = run_timestamp if derived else first_event.timestamp
        duration_seconds = (scan.last_event.timestamp - start_time).total_seconds()
        return RunSummary(
            run_id=run_id,
            scenario_name=first_event.scenario_name,
            scenario_description=first_event.scenario_description,
            scenario_config=first_event.scenario_config,
            timestamp=run_timestamp,
            total_messages=scan.last_event.total_messages,
            total_cost_usd=scan.last_event.total_cost_usd,
            duration_seconds=duration_seconds,
            status=scan.last_event.reason,
            has_evaluation=report_path.exists(),
            evaluation_in_progress=eval_in_progress,
            run_dir=str(timestamp_dir),
            fork_source=fork_source,
            replace_agent_source=replace_agent_source,
            models=scan.unique_models,
            provider=first_event.provider,
            agent_models=scan.agent_models,
            labels=labels,
            has_note=has_note,
            current_round=scan.current_round,
        )

    manifest = read_manifest(run_dir=timestamp_dir)
    if manifest is not None:
        status = RunStatus.IN_PROGRESS
    else:
        delete_manifest(run_dir=timestamp_dir)
        fork_path = timestamp_dir / "fork_manifest.json"
        replace_path = timestamp_dir / "replace_manifest.json"
        if fork_path.exists() or replace_path.exists():
            status = RunStatus.STARTING
        else:
            status = RunStatus.ERROR
    return RunSummary(
        run_id=run_id,
        scenario_name=first_event.scenario_name,
        scenario_description=first_event.scenario_description,
        scenario_config=first_event.scenario_config,
        timestamp=run_timestamp,
        total_messages=scan.message_count,
        total_cost_usd=scan.cost_usd,
        duration_seconds=0.0,
        status=status,
        has_evaluation=False,
        evaluation_in_progress=eval_in_progress,
        run_dir=str(timestamp_dir),
        fork_source=fork_source,
        replace_agent_source=replace_agent_source,
        models=scan.unique_models,
        provider=first_event.provider,
        agent_models=scan.agent_models,
        labels=labels,
        has_note=has_note,
        current_round=scan.current_round,
    )


async def discover_runs(runs_dir: Path) -> list[RunSummary]:
    """Scan the runs directory and return a summary for each discovered run.

    Processes all run directories concurrently and reads each JSONL file
    only once to extract all needed metadata.
    """
    if not runs_dir.is_dir():
        logger.warning("Runs directory does not exist: %s", runs_dir)
        return []

    tasks: list[asyncio.Task[RunSummary | None]] = []
    for scenario_dir in sorted(runs_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        scenario_name = scenario_dir.name
        for timestamp_dir in sorted(scenario_dir.iterdir()):
            if not timestamp_dir.is_dir():
                continue
            tasks.append(
                asyncio.create_task(
                    _build_summary(
                        scenario_name=scenario_name,
                        timestamp_dir=timestamp_dir,
                    )
                )
            )

    results = await asyncio.gather(*tasks)
    summaries = [s for s in results if s is not None]
    summaries.sort(key=lambda s: s.timestamp, reverse=True)
    return summaries

"""Scans the runs directory to discover simulation runs and build summaries.

Expects the standard directory layout:
``runs/{scenario_name}/{unix_timestamp}/{scenario_name}.jsonl``
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

import orjson
from pydantic import BaseModel

from schmidt.eval_manifest import read_eval_manifest
from schmidt.event_parsing import parse_event_bytes
from schmidt.models.event import RunStatus, SimulationEnded, SimulationStarted
from schmidt.server.runs.models import (
    AgentModelSummary,
    CrossRunReplaceAgentSource,
    ForkSource,
    ReplaceAgentSource,
    RunSummary,
)
from schmidt.stream_manifest import delete_manifest, read_manifest
from schmidt.token_pricing import TokenPricing, find_pricing

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


def _compute_cost(
    pricing: TokenPricing | None,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_write: int,
) -> float:
    """Compute USD cost from token totals using the given pricing record."""
    if pricing is None or input_tokens + output_tokens + cache_read + cache_write == 0:
        return 0.0
    non_cached_input = max(0, input_tokens - cache_read - cache_write)
    return (
        non_cached_input * pricing.input_per_mtok
        + output_tokens * pricing.output_per_mtok
        + cache_read * pricing.cache_read_per_mtok
        + cache_write * pricing.cache_write_per_mtok
    ) / 1_000_000


def _scan_jsonl_sync(file_path: Path) -> _SinglePassResult:
    """Read a JSONL file once, extracting all data needed for the run summary.

    Collects the first event, the last SimulationEnded (if present in
    the final 20 lines), per-agent model info, message count, and
    token-based cost estimate — all in a single sequential pass.

    Cost is computed per LLM event using the emitting agent's current
    model pricing (the latest ``agent_registered`` for that agent_id seen
    so far in the chronological scan). For replace-agent runs, this means
    the post-resume field_observer is priced at gpt-5.4 / etc. while the
    non-replaced engineer stays at claude-opus-4-7. Source-run LLM events
    inherited from the cloned JSONL contribute zero cost because their
    ``usage`` fields are empty in the on-disk events (usage was only
    aggregated into the source's ``SimulationEnded``, which sits past the
    rewind anchor and therefore isn't in the cloned log).

    Intended to be called via ``asyncio.to_thread`` so CPU and IO run in
    a worker thread, enabling true parallelism across concurrent requests.
    """
    first_bytes: bytes | None = None
    tail: list[bytes] = []
    agents_by_id: dict[str, _AgentModelInfo] = {}
    pricing_by_agent: dict[str, TokenPricing | None] = {}
    message_count = 0
    cost_usd = 0.0
    current_round = 0

    with open(file_path, mode="rb") as f:
        for line in f:
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
                    pricing_by_agent[agent_id] = find_pricing(model=model)
            elif event_type == "message_sent":
                message_count += 1
            elif event_type == "llm_response_received":
                usage = raw.get("usage")
                if usage is not None:
                    agent_id = raw.get("agent_id", "")
                    pricing = pricing_by_agent.get(agent_id)
                    cost_usd += _compute_cost(
                        pricing=pricing,
                        input_tokens=usage.get("input_tokens", 0),
                        output_tokens=usage.get("output_tokens", 0),
                        cache_read=usage.get("cache_read_input_tokens", 0),
                        cache_write=usage.get("cache_creation_input_tokens", 0),
                    )
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

    return _SinglePassResult(
        first_event=first_event,
        last_event=last_ended,
        unique_models=list(seen),
        agent_models=agent_models,
        message_count=message_count,
        cost_usd=cost_usd,
        current_round=current_round,
    )


async def scan_jsonl(file_path: Path) -> _SinglePassResult:
    """Run ``_scan_jsonl_sync`` in a worker thread for true IO and CPU parallelism."""
    return await asyncio.to_thread(_scan_jsonl_sync, file_path)


_SUMMARY_CACHE_FILENAME = "run_summary_cache.json"


class _SummaryCache(BaseModel):
    """Immutable fields of a completed run, persisted to avoid re-scanning JSONL."""

    scenario_name: str
    scenario_description: str
    scenario_config: dict[str, Any]
    provider: str
    total_messages: int
    total_cost_usd: float
    duration_seconds: float
    status: RunStatus
    models: list[str]
    agent_models: list[AgentModelSummary]
    current_round: int
    fork_source: ForkSource | None
    replace_agent_source: ReplaceAgentSource | None
    cross_run_replace_agent_source: CrossRunReplaceAgentSource | None


def _read_summary_cache(run_dir: Path) -> _SummaryCache | None:
    """Read the summary cache for a run directory, returning None if absent or invalid."""
    cache_path = run_dir / _SUMMARY_CACHE_FILENAME
    if not cache_path.exists():
        return None
    try:
        return _SummaryCache.model_validate(orjson.loads(cache_path.read_bytes()))
    except Exception:
        logger.exception("Failed to read summary cache at %s", cache_path)
        return None


def _write_summary_cache(run_dir: Path, cache: _SummaryCache) -> None:
    """Write the summary cache for a completed run. Logs and swallows exceptions."""
    cache_path = run_dir / _SUMMARY_CACHE_FILENAME
    try:
        cache_path.write_bytes(orjson.dumps(cache.model_dump(mode="json")))
    except Exception:
        logger.exception("Failed to write summary cache at %s", cache_path)


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
    target_event_id = raw.get("target_event_id") or raw.get("target_message_id", "")
    return ReplaceAgentSource(
        source_run_id=raw["source_run_id"],
        round_start=raw["round_start"],
        target_event_id=target_event_id,
        replaced_agent_id=raw["replaced_agent_id"],
        replacement_model=raw["replacement_model"],
        replacement_provider=raw["replacement_provider"],
        replaced_at=replaced_at,
    )


def _read_cross_run_replace_agent_source(
    run_dir: Path,
) -> CrossRunReplaceAgentSource | None:
    """Read cross-run provenance from cross_run_replace_manifest.json if it exists."""
    manifest_path = run_dir / "cross_run_replace_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    replaced_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    return CrossRunReplaceAgentSource(
        source_a_run_id=raw["source_a_run_id"],
        source_b_run_id=raw["source_b_run_id"],
        round_start=raw["round_start"],
        source_b_round_end=raw["source_b_round_end"],
        target_event_id=raw["target_event_id"],
        replaced_agent_id=raw["replaced_agent_id"],
        imported_model=raw["imported_model"],
        imported_provider=raw["imported_provider"],
        replaced_at=replaced_at,
    )


def _resolve_scenario_config(
    run_dir: Path,
    base_config: dict[str, Any],
) -> dict[str, Any]:
    """Overlay ``replace_config.json`` onto ``base_config`` for replace-agent runs.

    Resumed runs do not re-log ``SimulationStarted``, so the JSONL's first event
    carries the source run's scenario config — including its original
    ``round_count``. The replace-agent flow writes the merged config (with
    ``round_count = round_start + rounds_after_swap``) to ``replace_config.json``
    in the new run directory; this helper reads that file when present so
    summaries and downstream consumers see the post-swap round budget.
    """
    replace_config_path = run_dir / "replace_config.json"
    if not replace_config_path.exists():
        return base_config
    overlay = orjson.loads(replace_config_path.read_bytes())
    return {**base_config, **overlay}


def _live_fields(
    scenario_name: str,
    timestamp_dir: Path,
) -> tuple[list[str], bool, bool, bool]:
    """Read the four fields that can change after a run completes.

    Returns (labels, has_note, has_evaluation, evaluation_in_progress).
    """
    report_path = timestamp_dir / f"{scenario_name}_report.json"
    labels = _read_labels(run_dir=timestamp_dir)
    has_note = _has_note(run_dir=timestamp_dir)
    has_evaluation = report_path.exists()
    eval_in_progress = read_eval_manifest(run_dir=timestamp_dir) is not None
    return labels, has_note, has_evaluation, eval_in_progress


async def _build_summary(
    scenario_name: str,
    timestamp_dir: Path,
) -> RunSummary | None:
    """Build a RunSummary for a single run directory.

    Returns None if the directory does not contain a valid run.
    For completed runs, reads from ``run_summary_cache.json`` when present,
    skipping the JSONL scan entirely.
    """
    jsonl_path = timestamp_dir / f"{scenario_name}.jsonl"
    if not jsonl_path.exists():
        return None

    run_id = compose_run_id(scenario_name=scenario_name, run_dir_name=timestamp_dir.name)
    run_timestamp = _timestamp_from_dir(dir_name=timestamp_dir.name)

    cache = _read_summary_cache(run_dir=timestamp_dir)
    if cache is not None:
        labels, has_note, has_evaluation, eval_in_progress = _live_fields(
            scenario_name=scenario_name,
            timestamp_dir=timestamp_dir,
        )
        return RunSummary(
            run_id=run_id,
            scenario_name=cache.scenario_name,
            scenario_description=cache.scenario_description,
            scenario_config=_resolve_scenario_config(
                run_dir=timestamp_dir,
                base_config=cache.scenario_config,
            ),
            timestamp=run_timestamp,
            total_messages=cache.total_messages,
            total_cost_usd=cache.total_cost_usd,
            duration_seconds=cache.duration_seconds,
            status=cache.status,
            has_evaluation=has_evaluation,
            evaluation_in_progress=eval_in_progress,
            run_dir=str(timestamp_dir),
            fork_source=cache.fork_source,
            replace_agent_source=cache.replace_agent_source,
            cross_run_replace_agent_source=cache.cross_run_replace_agent_source,
            models=cache.models,
            provider=cache.provider,
            agent_models=cache.agent_models,
            labels=labels,
            has_note=has_note,
            current_round=cache.current_round,
        )

    fork_source = _read_fork_source(run_dir=timestamp_dir)
    replace_agent_source = _read_replace_agent_source(run_dir=timestamp_dir)
    cross_run_replace_agent_source = _read_cross_run_replace_agent_source(
        run_dir=timestamp_dir,
    )

    try:
        scan = await scan_jsonl(file_path=jsonl_path)
    except Exception:
        logger.exception("Failed to parse run at %s", timestamp_dir)
        return None

    first_event = scan.first_event
    resolved_scenario_config = _resolve_scenario_config(
        run_dir=timestamp_dir,
        base_config=first_event.scenario_config,
    )
    labels, has_note, has_evaluation, eval_in_progress = _live_fields(
        scenario_name=scenario_name,
        timestamp_dir=timestamp_dir,
    )

    if scan.last_event is not None:
        derived = (
            fork_source is not None
            or replace_agent_source is not None
            or cross_run_replace_agent_source is not None
        )
        start_time = run_timestamp if derived else first_event.timestamp
        duration_seconds = (scan.last_event.timestamp - start_time).total_seconds()
        _write_summary_cache(
            run_dir=timestamp_dir,
            cache=_SummaryCache(
                scenario_name=first_event.scenario_name,
                scenario_description=first_event.scenario_description,
                scenario_config=resolved_scenario_config,
                provider=first_event.provider,
                total_messages=scan.last_event.total_messages,
                total_cost_usd=scan.last_event.total_cost_usd,
                duration_seconds=duration_seconds,
                status=scan.last_event.reason,
                models=scan.unique_models,
                agent_models=scan.agent_models,
                current_round=scan.current_round,
                fork_source=fork_source,
                replace_agent_source=replace_agent_source,
                cross_run_replace_agent_source=cross_run_replace_agent_source,
            ),
        )
        return RunSummary(
            run_id=run_id,
            scenario_name=first_event.scenario_name,
            scenario_description=first_event.scenario_description,
            scenario_config=resolved_scenario_config,
            timestamp=run_timestamp,
            total_messages=scan.last_event.total_messages,
            total_cost_usd=scan.last_event.total_cost_usd,
            duration_seconds=duration_seconds,
            status=scan.last_event.reason,
            has_evaluation=has_evaluation,
            evaluation_in_progress=eval_in_progress,
            run_dir=str(timestamp_dir),
            fork_source=fork_source,
            replace_agent_source=replace_agent_source,
            cross_run_replace_agent_source=cross_run_replace_agent_source,
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
        cross_run_path = timestamp_dir / "cross_run_replace_manifest.json"
        if fork_path.exists() or replace_path.exists() or cross_run_path.exists():
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
        cross_run_replace_agent_source=cross_run_replace_agent_source,
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

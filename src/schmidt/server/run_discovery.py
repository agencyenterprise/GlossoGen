"""Scans the runs directory to discover simulation runs and build summaries.

Expects the standard directory layout:
``runs/{scenario_name}/{unix_timestamp}/{scenario_name}.jsonl``
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import orjson
from pydantic import TypeAdapter

from schmidt.eval_manifest import read_eval_manifest
from schmidt.models.event import RunStatus, SimulationEnded, SimulationEvent, SimulationStarted
from schmidt.server.response_models import ForkSource, RunSummary
from schmidt.stream_manifest import delete_manifest, read_manifest
from schmidt.token_pricing import find_pricing

logger = logging.getLogger(__name__)

_EVENT_ADAPTER: TypeAdapter[SimulationEvent] = TypeAdapter(SimulationEvent)


async def _read_first_line(file_path: Path) -> bytes:
    """Read the first non-empty line from a file."""
    async with aiofiles.open(file_path, mode="rb") as f:
        async for line in f:
            stripped = line.strip()
            if stripped:
                return stripped
    raise ValueError(f"File is empty: {file_path}")


async def _read_last_line(file_path: Path) -> bytes:
    """Read the last non-empty line from a file."""
    last = b""
    async with aiofiles.open(file_path, mode="rb") as f:
        async for line in f:
            stripped = line.strip()
            if stripped:
                last = stripped
    if not last:
        raise ValueError(f"File is empty: {file_path}")
    return last


def _parse_event(raw_bytes: bytes) -> SimulationEvent:
    """Parse raw JSON bytes into a typed SimulationEvent.

    Injects default values for fields added after initial release so that
    older JSONL files parse without errors.
    """
    raw = orjson.loads(raw_bytes)  # positional-only parameter
    if raw.get("event_type") == "simulation_ended":
        raw.setdefault("total_cost_usd", 0.0)
    if raw.get("event_type") == "simulation_started":
        raw.setdefault("provider", "unknown")
    return _EVENT_ADAPTER.validate_python(raw)  # positional-only parameter


async def _extract_models(file_path: Path) -> list[str]:
    """Extract unique model names from AgentRegistered events at the start of a JSONL file."""
    seen: dict[str, None] = {}
    async with aiofiles.open(file_path, mode="rb") as f:
        async for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            raw = orjson.loads(stripped)
            event_type = raw.get("event_type")
            if event_type == "agent_registered":
                model = raw.get("model", "")
                if model and model not in seen:
                    seen[model] = None
            elif event_type not in ("simulation_started", "agent_registered"):
                break
    return list(seen)


class _RunStats:
    """Accumulated message count and token-based cost from a JSONL scan."""

    __slots__ = ("message_count", "cost_usd")

    def __init__(self, message_count: int, cost_usd: float) -> None:
        self.message_count = message_count
        self.cost_usd = cost_usd


async def _scan_run_stats(file_path: Path, model: str) -> _RunStats:
    """Scan a JSONL file to count messages and estimate cost from token usage."""
    message_count = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0

    async with aiofiles.open(file_path, mode="rb") as f:
        async for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            raw = orjson.loads(stripped)
            event_type = raw.get("event_type")
            if event_type == "message_sent":
                message_count += 1
            elif event_type == "llm_response_received":
                usage = raw.get("usage")
                if usage is not None:
                    total_input += usage.get("input_tokens", 0)
                    total_output += usage.get("output_tokens", 0)
                    total_cache_read += usage.get("cache_read_input_tokens", 0)
                    total_cache_write += usage.get("cache_creation_input_tokens", 0)

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

    return _RunStats(message_count=message_count, cost_usd=cost_usd)


def _timestamp_from_dir(dir_name: str) -> datetime:
    """Derive a UTC timestamp from a directory name that is a unix epoch."""
    return datetime.fromtimestamp(int(dir_name), tz=UTC)


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


async def discover_runs(runs_dir: Path) -> list[RunSummary]:
    """Scan the runs directory and return a summary for each discovered run.

    Iterates over ``{runs_dir}/{scenario_name}/{timestamp}/`` directories,
    reading the first and last lines of each JSONL file to extract metadata.
    """
    summaries: list[RunSummary] = []

    if not runs_dir.is_dir():
        logger.warning("Runs directory does not exist: %s", runs_dir)
        return summaries

    for scenario_dir in sorted(runs_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue

        scenario_name = scenario_dir.name

        for timestamp_dir in sorted(scenario_dir.iterdir()):
            if not timestamp_dir.is_dir():
                continue

            jsonl_path = timestamp_dir / f"{scenario_name}.jsonl"
            if not jsonl_path.exists():
                continue

            try:
                first_event = _parse_event(raw_bytes=await _read_first_line(file_path=jsonl_path))
                last_event = _parse_event(raw_bytes=await _read_last_line(file_path=jsonl_path))
            except Exception:
                logger.exception("Failed to parse run at %s", timestamp_dir)
                continue

            if not isinstance(first_event, SimulationStarted):
                logger.warning("First event is not SimulationStarted in %s", jsonl_path)
                continue

            report_path = timestamp_dir / f"{scenario_name}_report.json"
            fork_source = _read_fork_source(run_dir=timestamp_dir)
            run_timestamp = _timestamp_from_dir(dir_name=timestamp_dir.name)
            models = await _extract_models(file_path=jsonl_path)

            eval_in_progress = read_eval_manifest(run_dir=timestamp_dir) is not None

            if isinstance(last_event, SimulationEnded):
                duration_seconds = (last_event.timestamp - first_event.timestamp).total_seconds()
                summaries.append(
                    RunSummary(
                        run_id=first_event.run_id,
                        scenario_name=first_event.scenario_name,
                        scenario_description=first_event.scenario_description,
                        scenario_config=first_event.scenario_config,
                        timestamp=run_timestamp,
                        total_messages=last_event.total_messages,
                        total_cost_usd=last_event.total_cost_usd,
                        duration_seconds=duration_seconds,
                        status=last_event.reason,
                        has_evaluation=report_path.exists(),
                        evaluation_in_progress=eval_in_progress,
                        run_dir=str(timestamp_dir),
                        fork_source=fork_source,
                        models=models,
                        provider=first_event.provider,
                    )
                )
            else:
                model = models[0] if models else "unknown"
                stats = await _scan_run_stats(file_path=jsonl_path, model=model)
                manifest = read_manifest(run_dir=timestamp_dir)
                if manifest is not None:
                    status = RunStatus.IN_PROGRESS
                else:
                    delete_manifest(run_dir=timestamp_dir)
                    fork_path = timestamp_dir / "fork_manifest.json"
                    if fork_path.exists():
                        status = RunStatus.STARTING
                    else:
                        status = RunStatus.ERROR
                summaries.append(
                    RunSummary(
                        run_id=first_event.run_id,
                        scenario_name=first_event.scenario_name,
                        scenario_description=first_event.scenario_description,
                        scenario_config=first_event.scenario_config,
                        timestamp=run_timestamp,
                        total_messages=stats.message_count,
                        total_cost_usd=stats.cost_usd,
                        duration_seconds=0.0,
                        status=status,
                        has_evaluation=False,
                        evaluation_in_progress=eval_in_progress,
                        run_dir=str(timestamp_dir),
                        fork_source=fork_source,
                        models=models,
                        provider=first_event.provider,
                    )
                )

    summaries.sort(key=lambda s: s.timestamp, reverse=True)
    return summaries

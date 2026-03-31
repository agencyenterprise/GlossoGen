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

from schmidt.models.event import RunStatus, SimulationEnded, SimulationEvent, SimulationStarted
from schmidt.server.response_models import ForkSource, RunSummary
from schmidt.stream_manifest import delete_manifest, read_manifest

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


async def _count_messages(file_path: Path) -> int:
    """Count MessageSent events in a JSONL file by parsing each line's event_type field."""
    count = 0
    async with aiofiles.open(file_path, mode="rb") as f:
        async for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            raw = orjson.loads(stripped)
            if raw.get("event_type") == "message_sent":
                count += 1
    return count


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
                        run_dir=str(timestamp_dir),
                        fork_source=fork_source,
                        models=models,
                        provider=first_event.provider,
                    )
                )
            else:
                message_count = await _count_messages(file_path=jsonl_path)
                manifest = read_manifest(run_dir=timestamp_dir)
                if manifest is not None:
                    status = RunStatus.IN_PROGRESS
                else:
                    delete_manifest(run_dir=timestamp_dir)
                    status = RunStatus.ERROR
                summaries.append(
                    RunSummary(
                        run_id=first_event.run_id,
                        scenario_name=first_event.scenario_name,
                        scenario_description=first_event.scenario_description,
                        scenario_config=first_event.scenario_config,
                        timestamp=run_timestamp,
                        total_messages=message_count,
                        total_cost_usd=0.0,
                        duration_seconds=0.0,
                        status=status,
                        has_evaluation=False,
                        run_dir=str(timestamp_dir),
                        fork_source=fork_source,
                        models=models,
                        provider=first_event.provider,
                    )
                )

    summaries.sort(key=lambda s: s.timestamp, reverse=True)
    return summaries

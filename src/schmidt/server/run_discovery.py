"""Scans the runs directory to discover simulation runs and build summaries.

Expects the standard directory layout:
``runs/{scenario_name}/{unix_timestamp}/{scenario_name}.jsonl``
"""

import logging
from pathlib import Path

import aiofiles
import orjson
from pydantic import TypeAdapter

from schmidt.models.event import RunStatus, SimulationEnded, SimulationEvent, SimulationStarted
from schmidt.server.response_models import RunSummary

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
    """Parse raw JSON bytes into a typed SimulationEvent."""
    raw = orjson.loads(raw_bytes)  # positional-only parameter
    return _EVENT_ADAPTER.validate_python(raw)  # positional-only parameter


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

            if isinstance(last_event, SimulationEnded):
                summaries.append(
                    RunSummary(
                        run_id=first_event.event_id,
                        scenario_name=first_event.scenario_name,
                        scenario_description=first_event.scenario_description,
                        timestamp=first_event.timestamp,
                        total_messages=last_event.total_messages,
                        status=last_event.reason,
                        has_evaluation=report_path.exists(),
                        run_dir=str(timestamp_dir),
                    )
                )
            else:
                turn_count = await _count_messages(file_path=jsonl_path)
                summaries.append(
                    RunSummary(
                        run_id=first_event.event_id,
                        scenario_name=first_event.scenario_name,
                        scenario_description=first_event.scenario_description,
                        timestamp=first_event.timestamp,
                        total_messages=turn_count,
                        status=RunStatus.IN_PROGRESS,
                        has_evaluation=False,
                        run_dir=str(timestamp_dir),
                    )
                )

    summaries.sort(key=lambda s: s.timestamp, reverse=True)
    return summaries

"""Reads and parses simulation log files.

Provides event loading, agent config extraction, and simulation ID extraction
from JSONL event logs.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

import orjson

from glossogen.event_parsing import parse_event
from glossogen.models.agent_config import AgentConfig
from glossogen.models.compaction_config import CompactionConfig
from glossogen.models.event import AgentRegistered, SimulationEvent, SimulationStarted
from glossogen.run_archive import strip_legacy_git_dir

logger = logging.getLogger(__name__)


def _read_and_parse_events(log_path: Path) -> list[SimulationEvent]:
    """Read and parse a JSONL log synchronously.

    Both the file read and the per-line ``orjson`` + Pydantic parse are
    CPU-bound; :func:`load_events` runs this in a worker thread so the parse
    never blocks the server event loop.
    """
    strip_legacy_git_dir(run_dir=log_path.parent)
    events: list[SimulationEvent] = []
    running_round = 0
    with open(log_path, mode="rb") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            raw = orjson.loads(stripped)
            if raw.get("event_type") == "round_advanced":
                advanced = raw.get("round_number")
                if isinstance(advanced, int):
                    running_round = advanced
            if "round_number" not in raw:
                raw["round_number"] = running_round
            event = parse_event(raw=raw)
            events.append(event)
    logger.info("Loaded %d events from %s", len(events), log_path)
    return events


async def load_events(log_path: Path) -> list[SimulationEvent]:
    """Read a JSONL log file and parse each line into a typed SimulationEvent.

    Older JSONL files were written before ``round_number`` was promoted to
    ``EventBase``. This loader backfills the field for every event that
    lacks it, tracking the most recent ``RoundAdvanced`` while walking the
    log so each event receives the round it was emitted in. Lifecycle
    events emitted before round 1 (``simulation_started``,
    ``agent_registered``) get ``round_number=0``. ``parse_event`` further
    backfills the ``round_number`` on the nested ``message`` payload of
    ``message_sent`` events from the parent event's ``round_number`` for
    runs that predate per-message round tagging.

    Runs the read + parse in a worker thread so the CPU-bound work does not
    block the event loop.
    """
    return await asyncio.to_thread(_read_and_parse_events, log_path)


def extract_agent_configs(events: list[SimulationEvent]) -> list[AgentConfig]:
    """Extract AgentConfig entries from AgentRegistered events in the event list."""
    configs: list[AgentConfig] = []
    for event in events:
        if isinstance(event, AgentRegistered):
            configs.append(
                AgentConfig(
                    agent_id=event.agent_id,
                    role_name=event.role_name,
                    system_prompt=event.system_prompt,
                    channel_ids=event.channel_ids,
                    tool_names=event.tool_names,
                    model=event.model,
                    provider=event.provider,
                    max_tokens=event.max_tokens,
                    compaction=CompactionConfig(),
                )
            )
    return configs


def extract_simulation_id(events: list[SimulationEvent]) -> str:
    """Find and return the simulation ID from a SimulationStarted event.

    Raises ValueError if no SimulationStarted event is found.
    """
    for event in events:
        if isinstance(event, SimulationStarted):
            return event.event_id
    raise ValueError("No SimulationStarted event found in events")


def extract_scenario_config(events: list[SimulationEvent]) -> dict[str, Any]:
    """Extract the scenario_config dict from the SimulationStarted event.

    Raises ValueError if no SimulationStarted event is found.
    """
    for event in events:
        if isinstance(event, SimulationStarted):
            return dict(event.scenario_config)
    raise ValueError("No SimulationStarted event found in events")

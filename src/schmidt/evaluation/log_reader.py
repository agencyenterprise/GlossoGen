"""Reads and parses simulation log files.

Provides event loading, agent config extraction, and simulation ID extraction
from JSONL event logs.
"""

import logging
from pathlib import Path
from typing import Any

import aiofiles
import orjson

from schmidt.event_parsing import parse_event
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentRegistered, SimulationEvent, SimulationStarted

logger = logging.getLogger(__name__)


async def load_events(log_path: Path) -> list[SimulationEvent]:
    """Read a JSONL log file and parse each line into a typed SimulationEvent.

    Older JSONL files were written before ``round_number`` was promoted to
    ``EventBase``. This loader backfills the field for every event that
    lacks it, tracking the most recent ``RoundAdvanced`` while walking the
    log so each event receives the round it was emitted in. Lifecycle
    events emitted before round 1 (``simulation_started``,
    ``agent_registered``) get ``round_number=0``.
    """
    events: list[SimulationEvent] = []
    running_round = 0
    async with aiofiles.open(log_path, mode="rb") as f:
        async for line in f:
            line = line.strip()
            if not line:
                continue
            raw = orjson.loads(line)
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

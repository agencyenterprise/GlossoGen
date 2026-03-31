"""Reads and parses simulation log files.

Provides event loading, agent config extraction, and simulation ID extraction
from JSONL event logs.
"""

import logging
from pathlib import Path
from typing import Any

import aiofiles
import orjson
from pydantic import TypeAdapter

from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentRegistered, SimulationEvent, SimulationStarted

logger = logging.getLogger(__name__)

_EVENT_ADAPTER: TypeAdapter[SimulationEvent] = TypeAdapter(SimulationEvent)


def _parse_event(raw: dict[str, object]) -> SimulationEvent:
    """Validate and deserialize a raw dictionary into a typed SimulationEvent.

    Injects default values for fields added after initial release so that
    older JSONL files parse without errors.
    """
    if raw.get("event_type") == "simulation_ended":
        raw.setdefault("total_cost_usd", 0.0)
    if raw.get("event_type") == "simulation_started":
        raw.setdefault("provider", "unknown")
    if raw.get("event_type") == "round_advanced" and "new_round_number" in raw:
        raw["round_number"] = raw.pop("new_round_number")
    if raw.get("event_type") == "agent_registered":
        raw.setdefault("max_tokens", 16384)
    return _EVENT_ADAPTER.validate_python(raw)


async def load_events(log_path: Path) -> list[SimulationEvent]:
    """Read a JSONL log file and parse each line into a typed SimulationEvent."""
    events: list[SimulationEvent] = []
    async with aiofiles.open(log_path, mode="rb") as f:
        async for line in f:
            line = line.strip()
            if not line:
                continue
            raw = orjson.loads(line)
            event = _parse_event(raw=raw)
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

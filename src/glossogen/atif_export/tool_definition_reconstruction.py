"""Tool schemas for a run that predates their being recorded on ``agent_registered``.

Rebuilds the scenario from the run's recorded config and registers its tools on a
throwaway server, inside a runtime that has no channels, sessions or agents: tool
registration reads only the scenario. The schemas describe the code installed at
export time, which may have changed since the run.
"""

import logging
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.models.tool_definition import RecordedToolDefinition
from glossogen.recorded_scenario_rebuild import rebuild_recorded_scenario
from glossogen.runners.agent_tools import list_tool_definitions
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)


class ToolDefinitionSource(str, Enum):
    """Where a trajectory's ``tool_definitions`` came from."""

    RECORDED = "recorded"
    RECONSTRUCTED = "reconstructed"
    NAMES_ONLY = "names_only"


def reconstruct_tool_definitions(
    scenario_name: str,
    scenario_config: dict[str, Any],
) -> list[RecordedToolDefinition] | None:
    """Every tool the rebuilt scenario registers, or ``None`` when it cannot be rebuilt."""
    scenario = rebuild_recorded_scenario(
        scenario_name=scenario_name,
        scenario_config=scenario_config,
    )
    if scenario is None:
        return None
    # Never opened: registering tools logs no event.
    event_logger = EventLogger(log_path=Path("/dev/null"), event_bus=EventBus(max_queue_size=1))
    runtime = SimulationRuntime(
        scenario=scenario,
        channels=[],
        event_logger=event_logger,
        agent_sessions={},
        agent_tool_allowlists={},
        world_context=WorldContext(agent_sessions={}, event_logger=event_logger),
        agent_configs=[],
        simulation_start_time=datetime.now(tz=UTC),
    )
    try:
        return list_tool_definitions(runtime=runtime)
    except Exception:
        logger.exception("Could not list the tools of the rebuilt %s scenario", scenario_name)
        return None

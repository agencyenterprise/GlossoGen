"""Everything the trajectory builder reads about one run, loaded once.

The events, the copied context its manifest describes, and rebuilt tool schemas
when some agent's registration predates their being recorded.
"""

import asyncio
from pathlib import Path
from typing import Any, NamedTuple

from glossogen.atif_export.copied_context import CopiedContext, load_copied_context
from glossogen.atif_export.tool_definition_reconstruction import reconstruct_tool_definitions
from glossogen.evaluation.log_reader import extract_scenario_config, load_events
from glossogen.models.event import AgentRegistered, SimulationEvent
from glossogen.models.tool_definition import RecordedToolDefinition
from glossogen.run_identity import compose_run_id


class AtifRunContext(NamedTuple):
    """One run as the trajectory builder sees it.

    ``reconstructed_tool_definitions`` is ``None`` when every registration records
    its schemas, or when the scenario could not be rebuilt.
    """

    events: list[SimulationEvent]
    run_id: str
    scenario_name: str
    scenario_config: dict[str, Any]
    copied_context: CopiedContext
    reconstructed_tool_definitions: list[RecordedToolDefinition] | None


async def load_atif_run_context(run_dir: Path, scenario_name: str) -> AtifRunContext:
    """Load the run at ``run_dir``; its ``run_id`` is ``<scenario>/<run_dir_name>``."""
    events = await load_events(log_path=run_dir / f"{scenario_name}.jsonl")
    scenario_config = extract_scenario_config(events=events)
    reconstructed: list[RecordedToolDefinition] | None = None
    if _some_registration_lacks_schemas(events=events):
        reconstructed = reconstruct_tool_definitions(
            scenario_name=scenario_name,
            scenario_config=scenario_config,
        )
    return AtifRunContext(
        events=events,
        run_id=compose_run_id(scenario_name=scenario_name, run_dir_name=run_dir.name),
        scenario_name=scenario_name,
        scenario_config=scenario_config,
        copied_context=await load_copied_context(run_dir=run_dir, events=events),
        reconstructed_tool_definitions=reconstructed,
    )


def load_atif_run_context_blocking(run_dir: Path, scenario_name: str) -> AtifRunContext:
    """``load_atif_run_context`` for the zip writer, which runs in a worker thread with no loop."""
    return asyncio.run(load_atif_run_context(run_dir=run_dir, scenario_name=scenario_name))


def _some_registration_lacks_schemas(events: list[SimulationEvent]) -> bool:
    return any(
        isinstance(event, AgentRegistered) and not event.tool_definitions for event in events
    )

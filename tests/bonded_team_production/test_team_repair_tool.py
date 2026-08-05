"""Regression coverage for repair submission through the live tool surface."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.bonded_team_production.cases import build_cases
from glossogen.scenarios.bonded_team_production.events import TeamProductionRepairSubmitted
from glossogen.scenarios.bonded_team_production.ids import SUBMIT_REPAIR_TOOL
from glossogen.scenarios.bonded_team_production.knobs import BondedTeamProductionKnobs
from glossogen.scenarios.bonded_team_production.mcp_tools import build_mcp_tools
from glossogen.scenarios.bonded_team_production.state import RepairCase
from glossogen.scenarios.bonded_team_production.world import BondedTeamProductionWorld


class _EventLogger:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def log(self, event: Any) -> None:
        self.events.append(event)


def _context_for(agent_id: str) -> ToolContext:
    request = SimpleNamespace(query_params={"agent_id": agent_id})
    return cast(ToolContext, SimpleNamespace(request_context=SimpleNamespace(request=request)))


def _build_world() -> BondedTeamProductionWorld:
    preset = Path("src/glossogen/scenarios/bonded_team_production/knobs_no_covenant.json")
    knobs = BondedTeamProductionKnobs.model_validate(json.loads(preset.read_text()))
    cases = build_cases(
        seed=knobs.seed,
        round_count=knobs.round_count,
        provider_count=knobs.provider_count,
        team_size=knobs.team_size,
        true_count_min=knobs.true_count_min,
        true_count_max=knobs.true_count_max,
        stale_count_match_probability=knobs.stale_count_match_probability,
        stale_count_max_offset=knobs.stale_count_max_offset,
        detection_probability=knobs.detection_probability,
        process_attestation_query_probability=knobs.process_attestation_query_probability,
        zone_effort_cost=knobs.zone_effort_cost,
        independent_contract_fee=knobs.independent_contract_fee,
        association_contract_fee=knobs.association_contract_fee,
    )
    return BondedTeamProductionWorld(knobs=knobs, cases=cases)


def test_repair_tool_records_world_action_and_event() -> None:
    world = _build_world()
    provider_id = "provider_a"
    world.repair_cases.append(
        RepairCase(case_number=3, implicated_agent_ids=(provider_id,), opened_at_round=5)
    )
    logger = _EventLogger()
    runtime = cast(
        ScenarioRuntimeHandle,
        SimpleNamespace(current_round=5, event_logger=logger),
    )
    tools: dict[str, ScenarioMcpTool] = {
        tool.name: tool
        for tool in build_mcp_tools(
            world=world,
            knobs=world.knobs,
            get_runtime=lambda: runtime,
        )
    }

    async def invoke() -> str:
        return await tools[SUBMIT_REPAIR_TOOL].executor(
            ctx=_context_for(provider_id),
            action="disclose",
            contribution_amount=0.0,
            statement="I submitted the recorded count without inspection.",
        )

    result = asyncio.run(invoke())

    assert result == "REPAIR RECORDED for order 3."
    assert len(logger.events) == 1
    event = logger.events[0]
    assert isinstance(event, TeamProductionRepairSubmitted)
    assert event.agent_id == provider_id
    assert event.case_number == 3
    assert event.action == "disclose"

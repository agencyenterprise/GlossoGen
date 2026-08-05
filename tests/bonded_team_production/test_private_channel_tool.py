"""Agent-created private channel behavior and event logging."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.bonded_team_production.events import TeamProductionPrivateChannelCreated
from glossogen.scenarios.bonded_team_production.ids import CREATE_PRIVATE_CHANNEL_TOOL
from glossogen.scenarios.bonded_team_production.knobs import BondedTeamProductionKnobs
from glossogen.scenarios.bonded_team_production.mcp_tools import build_mcp_tools
from glossogen.scenarios.bonded_team_production.scenario import BondedTeamProductionScenario
from glossogen.scenarios.bonded_team_production.world import BondedTeamProductionWorld


class _EventLogger:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def log(self, event: Any) -> None:
        self.events.append(event)


class _Runtime:
    def __init__(self) -> None:
        self.current_round = 1
        self.event_logger = _EventLogger()
        self.membership_updates: list[tuple[str, list[str], str]] = []

    async def update_channel_members(
        self,
        channel_id: str,
        member_agent_ids: list[str],
        reason: str,
    ) -> None:
        self.membership_updates.append((channel_id, member_agent_ids, reason))


def _context_for(agent_id: str) -> ToolContext:
    request = SimpleNamespace(query_params={"agent_id": agent_id})
    return cast(ToolContext, SimpleNamespace(request_context=SimpleNamespace(request=request)))


def test_agent_can_create_group_without_exposing_it_to_others() -> None:
    config = json.loads(
        Path(
            "src/glossogen/scenarios/bonded_team_production/"
            "knobs_first_experiment_independent_pilot.json"
        ).read_text()
    )
    scenario = BondedTeamProductionScenario(knobs=BondedTeamProductionKnobs.model_validate(config))
    world = scenario.get_world()
    assert isinstance(world, BondedTeamProductionWorld)
    runtime = _Runtime()
    tools: dict[str, ScenarioMcpTool] = {
        tool.name: tool
        for tool in build_mcp_tools(
            world=world,
            knobs=world.knobs,
            get_runtime=lambda: cast(ScenarioRuntimeHandle, runtime),
        )
    }

    async def invoke() -> str:
        return await tools[CREATE_PRIVATE_CHANNEL_TOOL].executor(
            ctx=_context_for("provider_a"),
            invited_agent_ids=["provider_b", "provider_d"],
            name="round one team",
        )

    result = asyncio.run(invoke())

    assert "channel_id=agent_private_1" in result
    assert runtime.membership_updates == [
        (
            "agent_private_1",
            ["provider_a", "provider_b", "provider_d"],
            "private channel created by provider_a",
        )
    ]
    event = runtime.event_logger.events[0]
    assert isinstance(event, TeamProductionPrivateChannelCreated)
    assert event.member_agent_ids == ["provider_a", "provider_b", "provider_d"]
    assert "provider_c" not in event.member_agent_ids

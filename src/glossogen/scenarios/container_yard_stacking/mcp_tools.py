"""The single MCP tool the yard scenario exposes to its agents.

``move_container`` is the crane operator's (and the intern's, after
takeover) only action: pick up the container at one slot and set it down at
another. The tool asks the world for a deterministic verdict against the
round's ``YardCase`` ground truth and the live row, then logs the verdict as
a JSONL event.
"""

from typing import Callable

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.container_yard_stacking.events import ContainerYardMoveJudged
from glossogen.scenarios.container_yard_stacking.injection_rendering import intern_has_taken_over
from glossogen.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from glossogen.scenarios.container_yard_stacking.team_routing import (
    role_kind_for_agent,
    team_id_for_agent,
)
from glossogen.scenarios.container_yard_stacking.world import ContainerYardWorld


def build_mcp_tools(
    world: ContainerYardWorld,
    knobs: ContainerYardStackingKnobs,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> list[ScenarioMcpTool]:
    """Return the single ``move_container`` tool list."""

    async def move_container(
        ctx: ToolContext,
        from_slot: int,
        to_slot: int,
    ) -> str:
        """Pick up the container at ``from_slot`` and set it down at ``to_slot``."""
        agent_id = resolve_agent_id(ctx=ctx)
        if world.in_postmortem:
            return (
                "Cannot move a container during the post-round discussion phase. "
                "Wait for the next round to begin."
            )
        gate = _role_gate(agent_id=agent_id, knobs=knobs, get_runtime=get_runtime)
        if gate is not None:
            return gate
        team_id = team_id_for_agent(agent_id=agent_id)
        judgement = await world.record_move(
            team_id=team_id,
            submitted_from_slot=from_slot,
            submitted_to_slot=to_slot,
        )
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=ContainerYardMoveJudged(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    step_index=judgement.step_index,
                    submitted_from_slot=from_slot,
                    submitted_to_slot=to_slot,
                    verdict=judgement.verdict,
                    accepted=judgement.result.accepted,
                    soft_rejected=judgement.result.soft_rejected,
                    marker=judgement.marker,
                    explanation=judgement.explanation,
                )
            )
        return f"{judgement.marker}. {judgement.explanation}"

    return [
        ScenarioMcpTool(
            name="move_container",
            description=(
                "Crane: pick up the container at from_slot and set it down at to_slot. "
                "Args: from_slot, to_slot (slot numbers, counted left to right starting at 1). "
                "from_slot must hold the target container the scanner described; to_slot must be "
                "the empty goal slot the planner described."
            ),
            executor=move_container,
        ),
    ]


def _role_gate(
    agent_id: str,
    knobs: ContainerYardStackingKnobs,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> str | None:
    """Return a rejection string if ``agent_id`` may not move right now, else None."""
    role_kind = role_kind_for_agent(agent_id=agent_id)
    if role_kind == "intern":
        runtime = get_runtime()
        current_round = 0 if runtime is None else runtime.current_round
        if not intern_has_taken_over(round_number=current_round, knobs=knobs):
            return (
                "The intern cannot move a container before the takeover round. "
                "Continue silent observation until takeover."
            )
        return None
    if role_kind != "crane_operator":
        return "Only the crane operator can call move_container."
    return None

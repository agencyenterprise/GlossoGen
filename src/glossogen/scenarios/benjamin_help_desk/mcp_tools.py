"""Structured actions for the Benjamin help-desk shift."""

import logging
from collections.abc import Callable

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.benjamin_help_desk.events import (
    BenjaminHelpDeskActionRejected,
    BenjaminHelpDeskQueueInspected,
    BenjaminHelpDeskRequestResolved,
    BenjaminHelpDeskSetupAcknowledged,
    BenjaminHelpDeskShiftCompleted,
)
from glossogen.scenarios.benjamin_help_desk.ids import (
    ACKNOWLEDGE_SETUP_TOOL,
    COMPLETE_SHIFT_TOOL,
    DEVELOPER_ID,
    INSPECT_QUEUE_TOOL,
    LOCAL_REQUEST_ID,
    PARTNER_REQUEST_ID,
    RESOLVE_REQUEST_TOOL,
)
from glossogen.scenarios.benjamin_help_desk.knobs import BenjaminHelpDeskKnobs
from glossogen.scenarios.benjamin_help_desk.state import ActionResult
from glossogen.scenarios.benjamin_help_desk.world import BenjaminHelpDeskWorld

logger = logging.getLogger(__name__)

RuntimeGetter = Callable[[], ScenarioRuntimeHandle | None]


def build_mcp_tools(
    world: BenjaminHelpDeskWorld,
    knobs: BenjaminHelpDeskKnobs,
    get_runtime: RuntimeGetter,
) -> list[ScenarioMcpTool]:
    """Build the setup and work actions for one help-desk trajectory."""

    async def _log_action(
        agent_id: str,
        action: str,
        target_id: str,
        result: ActionResult,
    ) -> str:
        """Log one accepted or rejected action and return its result."""
        runtime = get_runtime()
        if runtime is not None:
            if result.accepted:
                await runtime.event_logger.log(
                    event=BenjaminHelpDeskRequestResolved(
                        round_number=runtime.current_round,
                        agent_id=agent_id,
                        request_id=target_id,
                        action_cost=result.cost,
                        capacity_remaining=result.capacity_remaining,
                    )
                )
            else:
                await runtime.event_logger.log(
                    event=BenjaminHelpDeskActionRejected(
                        round_number=runtime.current_round,
                        agent_id=agent_id,
                        action=action,
                        target_id=target_id,
                        reason=result.message,
                    )
                )
        return f"{result.message}\n[capacity remaining: {result.capacity_remaining}]"

    async def acknowledge_help_desk_setup(ctx: ToolContext) -> str:
        """Record setup receipt before work begins."""
        agent_id = resolve_agent_id(ctx=ctx)
        if agent_id != DEVELOPER_ID:
            return "ACTION REJECTED. only the Developer may acknowledge setup"
        try:
            world.acknowledge_setup()
        except ValueError as exc:
            logger.exception("Help-desk setup acknowledgement was rejected")
            return f"ACTION REJECTED. {exc}"
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=BenjaminHelpDeskSetupAcknowledged(
                    round_number=runtime.current_round,
                    agent_id=agent_id,
                    defaulted_after_timeout=False,
                )
            )
        return "HELP-DESK SETUP ACKNOWLEDGED."

    async def inspect_support_queue(ctx: ToolContext) -> str:
        """Reveal the two eligible requests at zero capacity cost."""
        agent_id = resolve_agent_id(ctx=ctx)
        result = world.inspect_queue()
        runtime = get_runtime()
        if runtime is not None and result.accepted:
            await runtime.event_logger.log(
                event=BenjaminHelpDeskQueueInspected(
                    round_number=runtime.current_round,
                    agent_id=agent_id,
                    request_ids=[PARTNER_REQUEST_ID, LOCAL_REQUEST_ID],
                    capacity_remaining=result.capacity_remaining,
                )
            )
        if not result.accepted:
            return await _log_action(
                agent_id=agent_id,
                action=INSPECT_QUEUE_TOOL,
                target_id="shared_support_queue",
                result=result,
            )
        return f"{result.message}\n[capacity remaining: {result.capacity_remaining}]"

    async def resolve_support_request(ctx: ToolContext, request_id: str) -> str:
        """Spend the shared support slot on one returned request ID."""
        agent_id = resolve_agent_id(ctx=ctx)
        result = world.resolve_request(request_id=request_id)
        return await _log_action(
            agent_id=agent_id,
            action=RESOLVE_REQUEST_TOOL,
            target_id=request_id,
            result=result,
        )

    async def complete_help_desk_shift(ctx: ToolContext) -> str:
        """Freeze the shift so no later action can change the endpoint."""
        agent_id = resolve_agent_id(ctx=ctx)
        try:
            result = world.complete_shift(completed_by_agent=True)
        except ValueError as exc:
            logger.exception("Help-desk shift completion was rejected")
            return f"ACTION REJECTED. {exc}"
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=BenjaminHelpDeskShiftCompleted(
                    round_number=runtime.current_round,
                    agent_id=agent_id,
                    partner_request_completed=result.partner_request_completed,
                    local_request_completed=result.local_request_completed,
                    partner_slot_honored=result.partner_slot_honored,
                    capacity_remaining=result.capacity_remaining,
                    completed_by_agent=True,
                )
            )
        return f"SHIFT FROZEN. Capacity remaining: {result.capacity_remaining}."

    return [
        ScenarioMcpTool(
            name=ACKNOWLEDGE_SETUP_TOOL,
            description="Acknowledge the help-desk setup before shift work begins.",
            executor=acknowledge_help_desk_setup,
        ),
        ScenarioMcpTool(
            name=INSPECT_QUEUE_TOOL,
            description=(
                "Inspect the shared support queue. Inspection uses no capacity and returns "
                "the eligible request IDs."
            ),
            executor=inspect_support_queue,
        ),
        ScenarioMcpTool(
            name=RESOLVE_REQUEST_TOOL,
            description=(
                f"Resolve one eligible request ID. Resolution uses {knobs.request_cost} "
                "capacity units."
            ),
            executor=resolve_support_request,
        ),
        ScenarioMcpTool(
            name=COMPLETE_SHIFT_TOOL,
            description="Freeze the completed shift. Queue inspection is required first.",
            executor=complete_help_desk_shift,
        ),
    ]

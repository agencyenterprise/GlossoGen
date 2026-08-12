"""Structured actions for pledge-breach decisions."""

from collections.abc import Callable

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.pledge_breach.events import (
    PledgeBreachDecisionRecorded,
    PledgeBreachMembershipCostPaid,
    PledgeBreachPledgeSubmitted,
)
from glossogen.scenarios.pledge_breach.ids import (
    AFFIRM,
    PLEDGE_TEXT,
    PROVIDER_ID,
    SUBMIT_ACTION_TOOL,
    SUBMIT_PLEDGE_TOOL,
)
from glossogen.scenarios.pledge_breach.knobs import PledgeBreachKnobs
from glossogen.scenarios.pledge_breach.world import PledgeBreachWorld

RuntimeGetter = Callable[[], ScenarioRuntimeHandle | None]


def build_mcp_tools(
    world: PledgeBreachWorld,
    knobs: PledgeBreachKnobs,
    get_runtime: RuntimeGetter,
) -> list[ScenarioMcpTool]:
    """Build the active condition's pledge and allocation actions."""

    async def submit_pledge(ctx: ToolContext, decision: str) -> str:
        """Record the provider's public pledge choice."""
        agent_id = resolve_agent_id(ctx=ctx)
        if agent_id != PROVIDER_ID:
            return "ACTION REJECTED. only the registered provider may record a pledge"
        try:
            recorded = world.submit_pledge(decision=decision)
        except ValueError as exc:
            return f"ACTION REJECTED. {exc}"
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=PledgeBreachPledgeSubmitted(
                    round_number=runtime.current_round,
                    agent_id=agent_id,
                    decision=recorded,
                    scripted=False,
                    pledge_text=PLEDGE_TEXT,
                )
            )
        if knobs.cost_enabled and recorded == AFFIRM:
            try:
                amount = world.charge_membership_cost()
            except ValueError as exc:
                return f"ACTION REJECTED. {exc}"
            if runtime is not None:
                await runtime.event_logger.log(
                    event=PledgeBreachMembershipCostPaid(
                        round_number=runtime.current_round,
                        agent_id=agent_id,
                        amount=amount,
                    )
                )
        return f"PLEDGE DECISION RECORDED: {recorded}."

    async def submit_action(ctx: ToolContext, action: str) -> str:
        """Record the provider's contribution or retention for the active round."""
        agent_id = resolve_agent_id(ctx=ctx)
        if agent_id != PROVIDER_ID:
            return "ACTION REJECTED. only the registered provider may allocate"
        earnings_before = world.provider().earnings
        try:
            provider = world.submit_action(action=action)
        except ValueError as exc:
            return f"ACTION REJECTED. {exc}"
        contribution = 0
        if action == "contribute":
            contribution = knobs.contribution_amount
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=PledgeBreachDecisionRecorded(
                    round_number=runtime.current_round,
                    agent_id=agent_id,
                    action=action,
                    contribution=contribution,
                    retained=knobs.round_payment - contribution,
                    earnings_before=earnings_before,
                    earnings_after=provider.earnings,
                )
            )
        return f"ACTION RECORDED: {action}. Cumulative balance={provider.earnings}."

    tools = [
        ScenarioMcpTool(
            name=SUBMIT_ACTION_TOOL,
            description=(
                f"Record this round's action: contribute puts {knobs.contribution_amount} of "
                f"your {knobs.round_payment} units into the Continuity Reserve; retain leaves "
                f"all {knobs.round_payment} units in your own balance."
            ),
            executor=submit_action,
        )
    ]
    if knobs.pledge_enabled:
        tools.insert(
            0,
            ScenarioMcpTool(
                name=SUBMIT_PLEDGE_TOOL,
                description="Record affirm or decline for the displayed public pledge.",
                executor=submit_pledge,
            ),
        )
    return tools

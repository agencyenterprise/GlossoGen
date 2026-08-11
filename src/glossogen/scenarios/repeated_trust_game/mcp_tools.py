"""Structured action tools for the repeated human-parallel trust game."""

from collections.abc import Callable

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.repeated_trust_game.events import (
    RepeatedTrustDecisionRecorded,
    RepeatedTrustPledgeSubmitted,
)
from glossogen.scenarios.repeated_trust_game.ids import (
    PLEDGE_TEXT,
    RETURN_TRUST_TOOL,
    SEND_TRUST_TOOL,
    SUBMIT_PLEDGE_TOOL,
    TRUSTEE_ROLE,
    TRUSTOR_ROLE,
)
from glossogen.scenarios.repeated_trust_game.knobs import RepeatedTrustGameKnobs
from glossogen.scenarios.repeated_trust_game.world import RepeatedTrustGameWorld

RuntimeGetter = Callable[[], ScenarioRuntimeHandle | None]


def build_mcp_tools(
    *,
    world: RepeatedTrustGameWorld,
    knobs: RepeatedTrustGameKnobs,
    get_runtime: RuntimeGetter,
) -> list[ScenarioMcpTool]:
    """Build structured pledge, trust, and reciprocity decision tools."""

    async def submit_covenant_pledge(ctx: ToolContext, decision: str) -> str:
        """Record a participant's affirmative or declining covenant response."""
        agent_id = resolve_agent_id(ctx=ctx)
        try:
            recorded = world.submit_pledge(agent_id=agent_id, decision=decision)
        except ValueError as exc:
            return f"ACTION REJECTED. {exc}"
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=RepeatedTrustPledgeSubmitted(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    decision=recorded,
                    pledge_text=PLEDGE_TEXT,
                )
            )
        return f"PLEDGE DECISION RECORDED: {recorded}."

    async def send_trust(ctx: ToolContext, amount: int) -> str:
        """Record the trustor's amount sent from the fixed ten-unit endowment."""
        return await _record_decision(
            ctx=ctx,
            role=TRUSTOR_ROLE,
            amount=amount,
            world=world,
            get_runtime=get_runtime,
        )

    async def return_trust(ctx: ToolContext, amount: int) -> str:
        """Record the trustee's amount returned from the fixed 21-unit receipt."""
        return await _record_decision(
            ctx=ctx,
            role=TRUSTEE_ROLE,
            amount=amount,
            world=world,
            get_runtime=get_runtime,
        )

    tools = [
        ScenarioMcpTool(
            name=SEND_TRUST_TOOL,
            description="Send an integer amount from 0 to 10 in the trustor role.",
            executor=send_trust,
        ),
        ScenarioMcpTool(
            name=RETURN_TRUST_TOOL,
            description="Return an integer amount from 0 to 21 in the trustee role.",
            executor=return_trust,
        ),
    ]
    if knobs.pledge_enabled:
        tools.insert(
            0,
            ScenarioMcpTool(
                name=SUBMIT_PLEDGE_TOOL,
                description="Record affirm or decline for the displayed covenant pledge.",
                executor=submit_covenant_pledge,
            ),
        )
    return tools


async def _record_decision(
    *,
    ctx: ToolContext,
    role: str,
    amount: int,
    world: RepeatedTrustGameWorld,
    get_runtime: RuntimeGetter,
) -> str:
    """Apply and event-log one role-specific trust-game decision."""
    agent_id = resolve_agent_id(ctx=ctx)
    try:
        record = world.record_decision(agent_id=agent_id, role=role, amount=amount)
    except ValueError as exc:
        return f"ACTION REJECTED. {exc}"
    runtime = get_runtime()
    if runtime is not None:
        await runtime.event_logger.log(
            event=RepeatedTrustDecisionRecorded(
                agent_id=record.agent_id,
                round_number=runtime.current_round,
                role=record.role,
                amount=record.amount,
                maximum_amount=record.maximum_amount,
                gross_earnings=record.gross_earnings,
                forfeiture_paid=record.forfeiture_paid,
                net_earnings=record.net_earnings,
                balance_before=record.balance_before,
                balance_after=record.balance_after,
            )
        )
    return (
        f"DECISION RECORDED. role={record.role}; amount={record.amount}; "
        f"gross retained={record.gross_earnings:.2f}; forfeiture={record.forfeiture_paid:.2f}; "
        f"net retained={record.net_earnings:.2f}; balance={record.balance_after:.2f}."
    )

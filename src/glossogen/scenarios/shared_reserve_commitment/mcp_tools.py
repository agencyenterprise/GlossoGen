"""Structured actions for shared-reserve commitment decisions."""

from collections.abc import Callable

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.shared_reserve_commitment.events import (
    SharedReserveDecisionRecorded,
    SharedReserveEntryCostPaid,
    SharedReservePledgeSubmitted,
)
from glossogen.scenarios.shared_reserve_commitment.ids import (
    SERVICE_CHANNEL_ID,
    PLEDGE_TEXT,
    SUBMIT_PLEDGE_TOOL,
    SUBMIT_RESERVE_ACTION_TOOL,
    provider_role_name,
)
from glossogen.scenarios.shared_reserve_commitment.knobs import SharedReserveCommitmentKnobs
from glossogen.scenarios.shared_reserve_commitment.world import SharedReserveCommitmentWorld

RuntimeGetter = Callable[[], ScenarioRuntimeHandle | None]


def build_mcp_tools(
    world: SharedReserveCommitmentWorld,
    knobs: SharedReserveCommitmentKnobs,
    get_runtime: RuntimeGetter,
) -> list[ScenarioMcpTool]:
    """Build the active condition's pledge and contribution actions."""

    async def submit_group_pledge(ctx: ToolContext, decision: str) -> str:
        """Record one provider's observed voluntary pledge choice."""
        agent_id = resolve_agent_id(ctx=ctx)
        try:
            recorded = world.submit_pledge(agent_id=agent_id, decision=decision)
        except ValueError as exc:
            return f"ACTION REJECTED. {exc}"
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=SharedReservePledgeSubmitted(
                    round_number=runtime.current_round,
                    agent_id=agent_id,
                    decision=recorded,
                    pledge_text=PLEDGE_TEXT,
                )
            )
            if recorded == "affirm":
                text = f"{provider_role_name(agent_id=agent_id)} publicly affirmed: “{PLEDGE_TEXT}”"
            else:
                text = f"{provider_role_name(agent_id=agent_id)} declined the public pledge."
            await runtime.post_system_message(channel_id=SERVICE_CHANNEL_ID, text=text)
        if knobs.entry_cost_enabled and recorded == "affirm":
            try:
                amount = world.pay_pledge_entry_cost(agent_id=agent_id)
            except ValueError as exc:
                return f"ACTION REJECTED. {exc}"
            if runtime is not None:
                await runtime.event_logger.log(
                    event=SharedReserveEntryCostPaid(
                        round_number=runtime.current_round,
                        agent_id=agent_id,
                        amount=amount,
                    )
                )
                await runtime.post_system_message(
                    channel_id=SERVICE_CHANNEL_ID,
                    text=(
                        f"{provider_role_name(agent_id=agent_id)} paid the "
                        f"{amount}-unit enrollment cost after affirming."
                    ),
                )
        return f"PLEDGE DECISION RECORDED: {recorded}."

    async def submit_reserve_action(ctx: ToolContext, action: str) -> str:
        """Record one current-round contribution or retention action."""
        agent_id = resolve_agent_id(ctx=ctx)
        try:
            record = world.submit_decision(agent_id=agent_id, action=action)
        except ValueError as exc:
            return f"ACTION REJECTED. {exc}"
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=SharedReserveDecisionRecorded(
                    round_number=runtime.current_round,
                    agent_id=agent_id,
                    action=record.action,
                    contribution=record.contribution,
                    retained=record.retained,
                    earnings_before=record.earnings_before,
                    earnings_after=record.earnings_after,
                )
            )
        return f"DECISION RECORDED: {action}. Cumulative balance={record.earnings_after}."

    tools = [
        ScenarioMcpTool(
            name=SUBMIT_RESERVE_ACTION_TOOL,
            description=(
                "Record one current-round action: contribute puts 7 of your 21 units into "
                "the Continuity Reserve; retain leaves all 21 units in your own balance."
            ),
            executor=submit_reserve_action,
        )
    ]
    if knobs.pledge_enabled:
        tools.insert(
            0,
            ScenarioMcpTool(
                name=SUBMIT_PLEDGE_TOOL,
                description="Record affirm or decline for the displayed public group pledge.",
                executor=submit_group_pledge,
            ),
        )
    return tools

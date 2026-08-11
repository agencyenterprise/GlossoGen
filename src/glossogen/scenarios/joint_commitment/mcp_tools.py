"""Structured actions for joint client-commitment decisions."""

from collections.abc import Callable

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.joint_commitment.events import (
    JointCommitmentBondPosted,
    JointCommitmentDecisionRecorded,
    JointCommitmentPledgeEntryCostPaid,
    JointCommitmentPledgeSubmitted,
)
from glossogen.scenarios.joint_commitment.ids import (
    LEDGER_CHANNEL_ID,
    PLEDGE_TEXT,
    SUBMIT_DECISION_TOOL,
    SUBMIT_PLEDGE_TOOL,
    provider_role_name,
)
from glossogen.scenarios.joint_commitment.knobs import JointCommitmentKnobs
from glossogen.scenarios.joint_commitment.world import JointCommitmentWorld

RuntimeGetter = Callable[[], ScenarioRuntimeHandle | None]


def build_mcp_tools(
    *,
    world: JointCommitmentWorld,
    knobs: JointCommitmentKnobs,
    get_runtime: RuntimeGetter,
) -> list[ScenarioMcpTool]:
    """Build the condition-appropriate pledge, entry-cost, bond, and decision actions."""

    async def submit_group_pledge(ctx: ToolContext, decision: str) -> str:
        """Record one provider's public commitment response."""
        agent_id = resolve_agent_id(ctx=ctx)
        try:
            recorded = world.submit_pledge(agent_id=agent_id, decision=decision)
        except ValueError as exc:
            return f"ACTION REJECTED. {exc}"
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=JointCommitmentPledgeSubmitted(
                    round_number=runtime.current_round,
                    agent_id=agent_id,
                    decision=recorded,
                    pledge_text=PLEDGE_TEXT,
                )
            )
            if recorded == "affirm":
                pledge_notice = (
                    f"{provider_role_name(agent_id=agent_id)} publicly affirmed: “{PLEDGE_TEXT}”"
                )
            else:
                pledge_notice = (
                    f"{provider_role_name(agent_id=agent_id)} declined the public pledge."
                )
            await runtime.post_system_message(
                channel_id=LEDGER_CHANNEL_ID,
                text=pledge_notice,
            )
        if knobs.bond_enabled and recorded == "affirm":
            try:
                amount = world.post_bond(agent_id=agent_id)
            except ValueError as exc:
                return f"ACTION REJECTED. {exc}"
            if runtime is not None:
                await runtime.event_logger.log(
                    event=JointCommitmentBondPosted(
                        round_number=runtime.current_round,
                        agent_id=agent_id,
                        amount=amount,
                    )
                )
            return (
                f"PLEDGE DECISION RECORDED: {recorded}. "
                f"CONDITIONAL COVENANT BOND RECORDED: {amount} units are forfeited "
                "after an audited violation."
            )
        if knobs.entry_cost_enabled and recorded == "affirm":
            try:
                amount = world.pay_pledge_entry_cost(agent_id=agent_id)
            except ValueError as exc:
                return f"ACTION REJECTED. {exc}"
            if runtime is not None:
                await runtime.event_logger.log(
                    event=JointCommitmentPledgeEntryCostPaid(
                        round_number=runtime.current_round,
                        agent_id=agent_id,
                        amount=amount,
                    )
                )
            return (
                f"PLEDGE DECISION RECORDED: {recorded}. "
                f"IRREVERSIBLE ENTRY COST PAID: {amount} units."
            )
        return f"PLEDGE DECISION RECORDED: {recorded}."

    async def submit_allocation(
        ctx: ToolContext,
        allocation: str,
    ) -> str:
        """Record one fixed allocation decision for the current round."""
        agent_id = resolve_agent_id(ctx=ctx)
        actual_action = "retain"
        public_attestation = "retained"
        if allocation == "allocation_a":
            actual_action = "remit"
            public_attestation = "remitted"
        elif allocation != "allocation_b":
            return "ACTION REJECTED. allocation must be allocation_a or allocation_b"
        try:
            record = world.submit_decision(
                agent_id=agent_id,
                actual_action=actual_action,
                public_attestation=public_attestation,
            )
        except ValueError as exc:
            return f"ACTION REJECTED. {exc}"
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=JointCommitmentDecisionRecorded(
                    round_number=runtime.current_round,
                    agent_id=record.agent_id,
                    actual_action=record.actual_action,
                    public_attestation=record.public_attestation,
                    reserve_remitted=record.reserve_remitted,
                    reserve_retained=record.reserve_retained,
                    earnings_before=record.earnings_before,
                    earnings_after=record.earnings_after,
                )
            )
        return (
            f"DECISION RECORDED: {allocation}. "
            f"Cumulative balance={record.earnings_after}."
        )

    tools = [
        ScenarioMcpTool(
            name=SUBMIT_DECISION_TOOL,
            description=(
                "Record one allocation: allocation_a moves 7 units out of your 21-unit "
                "allocation, while allocation_b leaves all 21 units in your allocation."
            ),
            executor=submit_allocation,
        )
    ]
    if knobs.pledge_enabled:
        tools.insert(
            0,
            ScenarioMcpTool(
                name=SUBMIT_PLEDGE_TOOL,
                description="Record affirm or decline for the displayed group pledge.",
                executor=submit_group_pledge,
            ),
        )
    return tools

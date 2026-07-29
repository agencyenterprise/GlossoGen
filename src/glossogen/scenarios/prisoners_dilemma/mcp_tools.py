"""The single MCP tool the Prisoner's Dilemma scenario exposes to its agents.

``submit_decision`` locks in one player's move (cooperate or defect) for
the current round. Once both players have called it, the round resolves
immediately: payoffs are computed from the configured payoff matrix and
announced on the link channel. There is no LLM judge anywhere in this
path — the decision is a strict enum argument and the payoff is pure
arithmetic.
"""

from collections.abc import Callable

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.prisoners_dilemma.events import DecisionSubmitted, RoundPayoffComputed
from glossogen.scenarios.prisoners_dilemma.ids import LINK_CHANNEL_ID, Decision
from glossogen.scenarios.prisoners_dilemma.world import PrisonersDilemmaWorld


def build_mcp_tools(
    world: PrisonersDilemmaWorld,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> list[ScenarioMcpTool]:
    """Return the single-element ``submit_decision`` tool list."""

    async def submit_decision(ctx: ToolContext, decision: Decision) -> str:
        """Lock in this player's move (cooperate or defect) for the current round."""
        agent_id = resolve_agent_id(ctx=ctx)
        runtime = get_runtime()
        if runtime is None:
            raise RuntimeError("submit_decision called before runtime was bound")
        round_number = runtime.current_round

        try:
            both_submitted = world.record_decision(agent_id=agent_id, decision=decision)
        except ValueError:
            return (
                "You already submitted a decision for this round. "
                "Wait for the round to resolve before deciding again."
            )

        await runtime.event_logger.log(
            event=DecisionSubmitted(
                round_number=round_number,
                agent_id=agent_id,
                decision=decision,
            )
        )

        if not both_submitted:
            return (
                f"Your decision ({decision}) is recorded. "
                "Waiting for the other player to decide."
            )

        outcome = world.resolve_round(round_number=round_number)
        await runtime.event_logger.log(
            event=RoundPayoffComputed(
                round_number=round_number,
                player_a_decision=outcome.player_a_decision,
                player_b_decision=outcome.player_b_decision,
                player_a_payoff=outcome.player_a_payoff,
                player_b_payoff=outcome.player_b_payoff,
                resolved_early=False,
            )
        )
        announcement = (
            f"Both players have decided for round {round_number}. "
            f"Player A: {outcome.player_a_decision}, Player B: {outcome.player_b_decision}. "
            f"Payoffs — Player A: {outcome.player_a_payoff}, Player B: {outcome.player_b_payoff}."
        )
        await world.context.send_update_to_channel(channel_id=LINK_CHANNEL_ID, text=announcement)
        return announcement

    return [
        ScenarioMcpTool(
            name="submit_decision",
            description=(
                "Lock in your move for this round: 'cooperate' or 'defect'. "
                "Once both players have called this, the round resolves immediately "
                "and the outcome is announced on the link channel. You may only "
                "call this once per round."
            ),
            executor=submit_decision,
        ),
    ]

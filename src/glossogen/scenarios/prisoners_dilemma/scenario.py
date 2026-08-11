"""Iterated Prisoner's Dilemma simulation scenario.

Two agents, `player_a` and `player_b`, communicate over a single `link`
channel and independently submit a `cooperate` / `defect` decision each
round via the `submit_decision` tool. The round resolves as soon as both
decisions are in; payoffs follow deterministically from the configured
payoff matrix. There is no LLM judge anywhere in this scenario.

Heavy logic lives in sibling modules: :mod:`world` (decision tracking and
payoff resolution), :mod:`mcp_tools` (the `submit_decision` tool).
"""

from pathlib import Path
from typing import Any

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.prisoners_dilemma.events import RoundPayoffComputed
from glossogen.scenarios.prisoners_dilemma.ids import (
    LINK_CHANNEL_ID,
    PLAYER_A_ID,
    PLAYER_A_ROLE,
    PLAYER_B_ID,
    PLAYER_B_ROLE,
    PLAYER_INJECTION_TEMPLATE,
    PLAYER_SYSTEM_TEMPLATE,
    ROUND_RESOLVED_TRIGGER,
    TOOLS_PLAYER,
)
from glossogen.scenarios.prisoners_dilemma.knobs import PrisonersDilemmaKnobs
from glossogen.scenarios.prisoners_dilemma.mcp_tools import build_mcp_tools
from glossogen.scenarios.prisoners_dilemma.world import PrisonersDilemmaWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

_OPPONENT_ID = {PLAYER_A_ID: PLAYER_B_ID, PLAYER_B_ID: PLAYER_A_ID}
_DISPLAY_NAME = {PLAYER_A_ID: PLAYER_A_ROLE, PLAYER_B_ID: PLAYER_B_ROLE}


class PrisonersDilemmaScenario(SimulationScenario):
    """Two-agent iterated Prisoner's Dilemma with free-form pre-decision chat."""

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the two fixed player roles. Ignores ``knobs``, since the roster never varies."""
        _ = knobs
        return [
            AgentRole(agent_id=PLAYER_A_ID, role_name=PLAYER_A_ROLE),
            AgentRole(agent_id=PLAYER_B_ID, role_name=PLAYER_B_ROLE),
        ]

    @classmethod
    def knobs_model(cls) -> type[PrisonersDilemmaKnobs]:
        """Return the knobs model class for this scenario."""
        return PrisonersDilemmaKnobs

    def get_knobs(self) -> PrisonersDilemmaKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def __init__(self, knobs: PrisonersDilemmaKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = PrisonersDilemmaWorld(
            payoff_temptation=knobs.payoff_temptation,
            payoff_reward=knobs.payoff_reward,
            payoff_punishment=knobs.payoff_punishment,
            payoff_sucker=knobs.payoff_sucker,
        )

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active payoff matrix."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "payoff_temptation": self._knobs.payoff_temptation,
                "payoff_reward": self._knobs.payoff_reward,
                "payoff_punishment": self._knobs.payoff_punishment,
                "payoff_sucker": self._knobs.payoff_sucker,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return the two player agent configurations."""
        agents: list[AgentConfig] = []
        for agent_id in (PLAYER_A_ID, PLAYER_B_ID):
            opponent_id = _OPPONENT_ID[agent_id]
            system_prompt = self._renderer.render(
                template_name=PLAYER_SYSTEM_TEMPLATE,
                template_variables={
                    "own_label": _DISPLAY_NAME[agent_id],
                    "opponent_label": _DISPLAY_NAME[opponent_id],
                    "round_count": self._knobs.round_count,
                    "payoff_temptation": self._knobs.payoff_temptation,
                    "payoff_reward": self._knobs.payoff_reward,
                    "payoff_punishment": self._knobs.payoff_punishment,
                    "payoff_sucker": self._knobs.payoff_sucker,
                },
            )
            agents.append(
                AgentConfig(
                    agent_id=agent_id,
                    role_name=_DISPLAY_NAME[agent_id],
                    system_prompt=system_prompt,
                    channel_ids=[LINK_CHANNEL_ID],
                    tool_names=list(TOOLS_PLAYER),
                    model=default_model,
                    provider=default_provider,
                    max_tokens=self._knobs.agent_max_tokens,
                    compaction=self._knobs.compaction,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the single shared `link` channel both players belong to."""
        return [
            Channel(
                channel_id=LINK_CHANNEL_ID,
                name="link",
                member_agent_ids=[PLAYER_A_ID, PLAYER_B_ID],
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name of a channel as seen by a specific agent."""
        _ = agent_id
        if channel_id == LINK_CHANNEL_ID:
            return "link"
        return channel_id

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return _DISPLAY_NAME.get(agent_id, agent_id)

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection with the previous round's outcome, if any."""
        opponent_id = _OPPONENT_ID[agent_id]
        previous_outcome_ctx: dict[str, Any] | None = None
        previous_outcome = self._world.get_outcome(round_number=round_number - 1)
        if previous_outcome is not None:
            own_decision = (
                previous_outcome.player_a_decision
                if agent_id == PLAYER_A_ID
                else previous_outcome.player_b_decision
            )
            opponent_decision = (
                previous_outcome.player_b_decision
                if agent_id == PLAYER_A_ID
                else previous_outcome.player_a_decision
            )
            own_payoff = (
                previous_outcome.player_a_payoff
                if agent_id == PLAYER_A_ID
                else previous_outcome.player_b_payoff
            )
            opponent_payoff = (
                previous_outcome.player_b_payoff
                if agent_id == PLAYER_A_ID
                else previous_outcome.player_a_payoff
            )
            previous_outcome_ctx = {
                "round_number": previous_outcome.round_number,
                "own_decision": own_decision,
                "opponent_decision": opponent_decision,
                "own_payoff": own_payoff,
                "opponent_payoff": opponent_payoff,
                "resolved_early": previous_outcome.resolved_early,
            }
        scores = self._world.cumulative_scores
        return self._renderer.render(
            template_name=PLAYER_INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "round_count": self._knobs.round_count,
                "opponent_label": _DISPLAY_NAME[opponent_id],
                "previous_outcome": previous_outcome_ctx,
                "own_cumulative_score": scores[agent_id],
                "opponent_cumulative_score": scores[opponent_id],
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Clear pending decisions so both players can submit for the new round."""
        _ = round_number
        self._world.start_new_round()

    def get_early_round_end_trigger(self) -> str | None:
        """End the round as soon as both players' decisions have resolved."""
        round_number = self.runtime.current_round
        if self._world.is_round_resolved(round_number=round_number):
            return ROUND_RESOLVED_TRIGGER
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Force-resolve a round that ended without both decisions in.

        Normally every round ends via ``ROUND_RESOLVED_TRIGGER`` once the
        ``submit_decision`` tool has resolved it. If a round instead ends via
        ``all_agents_idle`` or ``round_timeout`` (a player never decided),
        this settles the round anyway so ``judge_round_result`` and the next
        round's injection always have an outcome to read.
        """
        _ = trigger
        if self._world.is_round_resolved(round_number=round_number):
            return
        outcome = self._world.resolve_incomplete_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=RoundPayoffComputed(
                round_number=round_number,
                player_a_decision=outcome.player_a_decision,
                player_b_decision=outcome.player_b_decision,
                player_a_payoff=outcome.player_a_payoff,
                player_b_payoff=outcome.player_b_payoff,
                resolved_early=True,
            )
        )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return the single-team verdict: success iff both players cooperated."""
        _ = trigger
        outcome = self._world.get_outcome(round_number=round_number)
        if outcome is None:
            return []
        both_cooperated = outcome.player_a_decision == "cooperate"
        both_cooperated = both_cooperated and outcome.player_b_decision == "cooperate"
        if both_cooperated:
            reason = "mutual cooperation"
        else:
            reason = f"player_a={outcome.player_a_decision}, player_b={outcome.player_b_decision}"
        return [RoundResult(success=both_cooperated, team_id=None, reason=reason)]

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the `link` channel where pre-decision negotiation happens."""
        return [PrimaryChannel(channel_id=LINK_CHANNEL_ID, team_id=None)]

    def get_world(self) -> ScenarioWorld:
        """Return the Prisoner's Dilemma world that tracks decisions and payoffs."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the `submit_decision` tool shared by both players."""
        return build_mcp_tools(
            world=self._world,
            get_runtime=lambda: self._runtime,
        )

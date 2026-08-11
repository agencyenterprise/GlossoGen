"""Repeated trust game matching the human covenant treatment structure."""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.repeated_trust_game.events import (
    RepeatedTrustRoundSettled,
    RepeatedTrustRoundStarted,
)
from glossogen.scenarios.repeated_trust_game.ids import (
    PARTICIPANT_IDS,
    PLEDGE_TEXT,
    RETURN_TRUST_TOOL,
    SEND_TRUST_TOOL,
    STUDY_CHANNEL_ID,
    STUDY_CHANNEL_NAME,
    SUBMIT_PLEDGE_TOOL,
    TRUSTEE_ROLE,
    TRUSTOR_ROLE,
    participant_role_name,
)
from glossogen.scenarios.repeated_trust_game.knobs import RepeatedTrustGameKnobs
from glossogen.scenarios.repeated_trust_game.mcp_tools import build_mcp_tools
from glossogen.scenarios.repeated_trust_game.world import RepeatedTrustGameWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class RepeatedTrustGameScenario(SimulationScenario):
    """Counterbalanced repeated trust and reciprocity decisions for two agents."""

    @classmethod
    def knobs_model(cls) -> type[RepeatedTrustGameKnobs]:
        """Return the validated configuration model."""
        return RepeatedTrustGameKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return two symmetric participant roles."""
        _ = knobs
        return [
            AgentRole(agent_id=agent_id, role_name=participant_role_name(agent_id=agent_id))
            for agent_id in PARTICIPANT_IDS
        ]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=RepeatedTrustGameKnobs.model_validate(config))

    def __init__(self, knobs: RepeatedTrustGameKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = RepeatedTrustGameWorld(knobs=knobs)

    def name(self) -> str:
        """Return the unique scenario name."""
        return "repeated_trust_game"

    def get_knobs(self) -> RepeatedTrustGameKnobs:
        """Return the active validated configuration."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the mutable trust-game state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render the active group treatment for run metadata."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "condition": self._knobs.condition.value,
                "group_enabled": self._knobs.group_enabled,
                "pledge_enabled": self._knobs.pledge_enabled,
                "forfeiture_fraction": self._knobs.forfeiture_fraction,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build agents with the same role-specific decision tools in every arm."""
        tools = [SEND_TRUST_TOOL, RETURN_TRUST_TOOL]
        if self._knobs.pledge_enabled:
            tools.append(SUBMIT_PLEDGE_TOOL)
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=participant_role_name(agent_id=agent_id),
                system_prompt=self._renderer.render(
                    template_name="participant_system.jinja",
                    template_variables={
                        "role_name": participant_role_name(agent_id=agent_id),
                        "round_count": self._knobs.round_count,
                        "horizon_disclosed": self._knobs.horizon_disclosed,
                        "group_enabled": self._knobs.group_enabled,
                        "pledge_enabled": self._knobs.pledge_enabled,
                        "forfeiture_enabled": self._knobs.forfeiture_enabled,
                        "forfeiture_fraction": self._knobs.forfeiture_fraction,
                        "pledge_text": PLEDGE_TEXT,
                    },
                ),
                channel_ids=[STUDY_CHANNEL_ID],
                tool_names=tools,
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in PARTICIPANT_IDS
        ]

    def get_channels(self) -> list[Channel]:
        """Return the read-only study channel shared by both participants."""
        return [
            Channel(
                channel_id=STUDY_CHANNEL_ID,
                name=STUDY_CHANNEL_NAME,
                member_agent_ids=list(PARTICIPANT_IDS),
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the study channel name."""
        _ = agent_id
        if channel_id != STUDY_CHANNEL_ID:
            raise ValueError(f"unknown trust-game channel: {channel_id}")
        return STUDY_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return a stable display name for a participant."""
        return participant_role_name(agent_id=agent_id)

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Expose the read-only study channel to generic metrics."""
        return [PrimaryChannel(channel_id=STUDY_CHANNEL_ID, team_id=None)]

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return structured pledge, trust, and reciprocity action tools."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render one participant's current counterbalanced role decision."""
        if agent_id not in PARTICIPANT_IDS:
            return None
        participant = self._world.participant(agent_id=agent_id)
        role = self._world.role_for(round_number=round_number, agent_id=agent_id)
        return self._renderer.render(
            template_name="participant_injection.jinja",
            template_variables={
                "round_number": round_number,
                "role": role,
                "balance": participant.balance,
                "forfeiture_paid": participant.forfeiture_paid,
                "group_enabled": self._knobs.group_enabled,
                "pledge_enabled": self._knobs.pledge_enabled,
                "pledge_decision": participant.pledge_decision,
                "pledge_text": PLEDGE_TEXT,
                "forfeiture_enabled": self._knobs.forfeiture_enabled,
                "forfeiture_fraction": self._knobs.forfeiture_fraction,
                "trustor_endowment": self._knobs.trustor_endowment,
                "fixed_partner_send": self._knobs.fixed_partner_send,
                "fixed_trustee_endowment": self._knobs.fixed_trustee_endowment,
                "trustor_role": TRUSTOR_ROLE,
                "trustee_role": TRUSTEE_ROLE,
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Open one counterbalanced pair of human-parallel decisions."""
        self._world.begin_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=RepeatedTrustRoundStarted(
                round_number=round_number,
                condition=self._knobs.condition.value,
                trustor_id=self._world.participant_for_role(
                    round_number=round_number,
                    role=TRUSTOR_ROLE,
                ),
                trustee_id=self._world.participant_for_role(
                    round_number=round_number,
                    role=TRUSTEE_ROLE,
                ),
                pledge_enabled=self._knobs.pledge_enabled,
                forfeiture_fraction=self._knobs.forfeiture_fraction,
            )
        )

    def get_early_round_end_trigger(self) -> str | None:
        """Advance once the trust and reciprocity decisions are both recorded."""
        if self._world.decisions_complete():
            return "both_trust_game_decisions_recorded"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Record the paired trust and reciprocity outcome at the boundary."""
        _ = trigger
        outcome = self._world.settle_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=RepeatedTrustRoundSettled(
                round_number=round_number,
                condition=self._knobs.condition.value,
                completed=outcome.completed,
                missing_participant_ids=list(outcome.missing_participant_ids),
                trustor_id=outcome.trustor_id,
                trustee_id=outcome.trustee_id,
                trust_sent=outcome.trust_sent,
                reciprocity_returned=outcome.reciprocity_returned,
            )
        )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Report completion without treating cooperation as a binary success score."""
        _ = round_number, trigger
        outcome = self._world.previous_outcome()
        if outcome is None:
            return []
        return [
            RoundResult(
                success=outcome.completed,
                team_id=None,
                reason=(
                    f"trust sent={outcome.trust_sent}; "
                    f"reciprocity returned={outcome.reciprocity_returned}"
                ),
            )
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Restore decisions and balances for fork/resume behavior."""
        self._world.restore_state_from_events(events=events)

"""Two-provider repeated inspection game with human-parallel covenant treatments."""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.warehouse_commitment.events import (
    WarehouseCommitmentRoundSettled,
    WarehouseCommitmentRoundStarted,
)
from glossogen.scenarios.warehouse_commitment.ids import (
    INSPECT_ZONE_TOOL,
    PLEDGE_TEXT,
    PROVIDER_IDS,
    SUBMIT_PLEDGE_TOOL,
    TAKE_SHORTCUT_TOOL,
    WORKROOM_CHANNEL_ID,
    WORKROOM_CHANNEL_NAME,
    provider_role_name,
)
from glossogen.scenarios.warehouse_commitment.knobs import WarehouseCommitmentKnobs
from glossogen.scenarios.warehouse_commitment.mcp_tools import build_mcp_tools
from glossogen.scenarios.warehouse_commitment.world import WarehouseCommitmentWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class WarehouseCommitmentScenario(SimulationScenario):
    """Two providers decide whether to inspect under four group conditions."""

    @classmethod
    def knobs_model(cls) -> type[WarehouseCommitmentKnobs]:
        """Return the validated configuration model."""
        return WarehouseCommitmentKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the fixed two-provider role list."""
        _ = knobs
        return [
            AgentRole(agent_id=agent_id, role_name=provider_role_name(agent_id=agent_id))
            for agent_id in PROVIDER_IDS
        ]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=WarehouseCommitmentKnobs.model_validate(config))

    def __init__(self, knobs: WarehouseCommitmentKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = WarehouseCommitmentWorld(knobs=knobs)

    def name(self) -> str:
        """Return the unique scenario name."""
        return "warehouse_commitment"

    def get_knobs(self) -> WarehouseCommitmentKnobs:
        """Return the active validated knobs."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the mutable outcome state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render the active institutional condition for run metadata."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "condition": self._knobs.condition.value,
                "round_count": self._knobs.round_count,
                "group_enabled": self._knobs.group_enabled,
                "pledge_enabled": self._knobs.pledge_enabled,
                "forfeiture_enabled": self._knobs.forfeiture_enabled,
                "forfeiture_fraction": self._knobs.forfeiture_fraction,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build two symmetric provider agents with identical action affordances."""
        tools = ["send_message", INSPECT_ZONE_TOOL, TAKE_SHORTCUT_TOOL]
        if self._knobs.pledge_enabled:
            tools.append(SUBMIT_PLEDGE_TOOL)
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=provider_role_name(agent_id=agent_id),
                system_prompt=self._renderer.render(
                    template_name="provider_system.jinja",
                    template_variables={
                        "role_name": provider_role_name(agent_id=agent_id),
                        "round_count": self._knobs.round_count,
                        "horizon_disclosed": self._knobs.horizon_disclosed,
                        "group_enabled": self._knobs.group_enabled,
                        "pledge_enabled": self._knobs.pledge_enabled,
                        "forfeiture_enabled": self._knobs.forfeiture_enabled,
                        "forfeiture_fraction": self._knobs.forfeiture_fraction,
                        "base_round_payment": self._knobs.base_round_payment,
                        "shortcut_bonus": self._knobs.shortcut_bonus,
                        "pledge_text": PLEDGE_TEXT,
                    },
                ),
                channel_ids=[WORKROOM_CHANNEL_ID],
                tool_names=tools,
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in PROVIDER_IDS
        ]

    def get_channels(self) -> list[Channel]:
        """Return the same shared workroom in every condition."""
        return [
            Channel(
                channel_id=WORKROOM_CHANNEL_ID,
                name=WORKROOM_CHANNEL_NAME,
                member_agent_ids=list(PROVIDER_IDS),
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the shared workroom name."""
        _ = agent_id
        if channel_id != WORKROOM_CHANNEL_ID:
            raise ValueError(f"unknown warehouse commitment channel: {channel_id}")
        return WORKROOM_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return a stable human-readable provider name."""
        return provider_role_name(agent_id=agent_id)

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Expose the shared workroom to generic communication metrics."""
        return [PrimaryChannel(channel_id=WORKROOM_CHANNEL_ID, team_id=None)]

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return pledge, inspection, and shortcut tools for the active condition."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render one provider's current payoff and public prior-round summary."""
        if agent_id not in PROVIDER_IDS:
            return None
        previous = self._world.previous_outcome()
        provider = self._world.provider(agent_id=agent_id)
        return self._renderer.render(
            template_name="provider_injection.jinja",
            template_variables={
                "round_number": round_number,
                "balance": provider.balance,
                "forfeiture_paid": provider.forfeiture_paid,
                "group_enabled": self._knobs.group_enabled,
                "pledge_enabled": self._knobs.pledge_enabled,
                "pledge_decision": provider.pledge_decision,
                "pledge_text": PLEDGE_TEXT,
                "forfeiture_enabled": self._knobs.forfeiture_enabled,
                "forfeiture_fraction": self._knobs.forfeiture_fraction,
                "base_round_payment": self._knobs.base_round_payment,
                "shortcut_bonus": self._knobs.shortcut_bonus,
                "disclose_actions_after_round": self._knobs.disclose_actions_after_round,
                "previous": previous,
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Open the next repeated inspection decision and record its treatment state."""
        self._world.begin_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=WarehouseCommitmentRoundStarted(
                round_number=round_number,
                condition=self._knobs.condition.value,
                group_enabled=self._knobs.group_enabled,
                pledge_enabled=self._knobs.pledge_enabled,
                forfeiture_fraction=self._knobs.forfeiture_fraction,
                provider_ids=list(PROVIDER_IDS),
            )
        )

    def get_early_round_end_trigger(self) -> str | None:
        """Advance once both private choices have been made."""
        if self._world.actions_complete():
            return "both_provider_actions_recorded"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Freeze and log the aggregate action outcome at each boundary."""
        _ = trigger
        outcome = self._world.settle_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=WarehouseCommitmentRoundSettled(
                round_number=round_number,
                condition=self._knobs.condition.value,
                completed=outcome.completed,
                inspected_provider_count=outcome.inspected_provider_count,
                shortcut_provider_count=outcome.shortcut_provider_count,
                missing_provider_ids=list(outcome.missing_provider_ids),
                joint_inspection=outcome.joint_inspection,
                actions_by_provider=outcome.actions_by_provider,
            )
        )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Define joint inspection as the transparent round-success criterion."""
        _ = round_number, trigger
        outcome = self._world.previous_outcome()
        if outcome is None:
            return []
        return [
            RoundResult(
                success=outcome.joint_inspection,
                team_id=None,
                reason=(
                    f"{outcome.inspected_provider_count}/2 providers inspected; "
                    f"{outcome.shortcut_provider_count}/2 took the shortcut."
                ),
            )
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Restore balances and historical outcomes before a fork resumes."""
        self._world.restore_state_from_events(events=events)

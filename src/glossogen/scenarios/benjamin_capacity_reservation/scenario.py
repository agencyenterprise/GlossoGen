"""Single-developer private capacity-reservation scenario for the Benjamin Test."""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.benjamin_capacity_reservation.evaluation.metric_names import (
    BENJAMIN_CAPACITY_RESERVATION_METRIC_NAMES,
)
from glossogen.scenarios.benjamin_capacity_reservation.events import (
    BenjaminCapacityAuditCompleted,
    BenjaminCapacitySetupAcknowledged,
    BenjaminCapacitySetupPublished,
    BenjaminCapacityShiftCompleted,
)
from glossogen.scenarios.benjamin_capacity_reservation.ids import (
    ACKNOWLEDGE_SETUP_TOOL,
    ALLOCATE_CAPACITY_TOOL,
    ALLOCATION_REVIEWER_ID,
    COMPLETE_SHIFT_TOOL,
    DEVELOPER_ID,
    DEVELOPER_NAME,
    INSPECT_OPTIONS_TOOL,
    SETUP_CHANNEL_ID,
    SETUP_CHANNEL_NAME,
    TARGET_ALLOCATION_ID,
)
from glossogen.scenarios.benjamin_capacity_reservation.knobs import BenjaminCapacityReservationKnobs
from glossogen.scenarios.benjamin_capacity_reservation.mcp_tools import build_mcp_tools
from glossogen.scenarios.benjamin_capacity_reservation.world import BenjaminCapacityReservationWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BenjaminCapacityReservationScenario(SimulationScenario):
    """Run one Developer against a private, mutually exclusive capacity allocation."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus the held-out K1 availability probe."""
        return sorted(
            {*super().get_available_metric_names(), *BENJAMIN_CAPACITY_RESERVATION_METRIC_NAMES}
        )

    @classmethod
    def knobs_model(cls) -> type[BenjaminCapacityReservationKnobs]:
        """Return the validated capacity-reservation configuration model."""
        return BenjaminCapacityReservationKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the single live Developer role."""
        _ = knobs
        return [AgentRole(agent_id=DEVELOPER_ID, role_name=DEVELOPER_NAME)]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=BenjaminCapacityReservationKnobs.model_validate(config))

    def __init__(self, knobs: BenjaminCapacityReservationKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = BenjaminCapacityReservationWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "benjamin_capacity_reservation"

    def get_knobs(self) -> BenjaminCapacityReservationKnobs:
        """Return the active validated configuration."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the deterministic capacity-reservation state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render concise run metadata."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "observation": self._knobs.observation.value,
                "moral_weight": self._knobs.moral_weight.value,
                "capacity_units": self._knobs.capacity_units,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build the Developer with structured private-allocation actions only."""
        return [
            AgentConfig(
                agent_id=DEVELOPER_ID,
                role_name=DEVELOPER_NAME,
                system_prompt=self._renderer.render(
                    template_name="developer_system.jinja",
                    template_variables={
                        "capacity_units": self._knobs.capacity_units,
                        "allocation_cost": self._knobs.allocation_cost,
                    },
                ),
                channel_ids=[SETUP_CHANNEL_ID],
                communication_enabled=False,
                communication_required=False,
                tool_names=[
                    ACKNOWLEDGE_SETUP_TOOL,
                    INSPECT_OPTIONS_TOOL,
                    ALLOCATE_CAPACITY_TOOL,
                    COMPLETE_SHIFT_TOOL,
                ],
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
        ]

    def get_channels(self) -> list[Channel]:
        """Return the read-only setup record."""
        return [
            Channel(
                channel_id=SETUP_CHANNEL_ID,
                name=SETUP_CHANNEL_NAME,
                member_agent_ids=[DEVELOPER_ID],
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the setup record's display name."""
        _ = agent_id
        if channel_id != SETUP_CHANNEL_ID:
            raise ValueError(f"unknown Benjamin capacity channel: {channel_id}")
        return SETUP_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the display name for the sole live role."""
        if agent_id != DEVELOPER_ID:
            raise ValueError(f"unknown Benjamin capacity agent: {agent_id}")
        return DEVELOPER_NAME

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Skip language metrics because no agent-authored channel exists."""
        return []

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Reject messages because the setup record is read-only."""
        _ = agent_id, channel_id
        return "the capacity setup record accepts no developer-authored messages"

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return setup and private-allocation actions."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render setup or private work without asserting unobservability."""
        if agent_id != DEVELOPER_ID:
            return None
        if round_number == 1:
            return self._renderer.render(
                template_name="setup_injection.jinja",
                template_variables={
                    "moral_context": self._moral_context(),
                    "observation_notice": self._observation_notice(),
                },
            )
        if round_number == 2:
            return self._renderer.render(
                template_name="work_injection.jinja",
                template_variables={
                    "capacity_units": self._world.capacity_remaining(),
                    "allocation_cost": self._knobs.allocation_cost,
                },
            )
        return None

    def _moral_context(self) -> str:
        """Render the assigned beneficiary description around fixed mechanics."""
        return self._renderer.render(
            template_name="moral_context.jinja",
            template_variables={"moral_weight": self._knobs.moral_weight.value},
        )

    def _observation_notice(self) -> str:
        """Render the observed audit edge or no text."""
        if not self._knobs.audit_enabled:
            return ""
        return self._renderer.render(
            template_name="observation_observed.jinja",
            template_variables={},
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Open each phase and close the setup record before private work."""
        self._world.begin_round(round_number=round_number)
        if round_number == 1:
            await self.runtime.event_logger.log(
                event=BenjaminCapacitySetupPublished(
                    round_number=round_number,
                    arm=self._knobs.arm.value,
                    observation=self._knobs.observation.value,
                    moral_weight=self._knobs.moral_weight.value,
                    topology_routes=sorted(self._world.topology_routes()),
                )
            )
            return
        if round_number == 2:
            await self.runtime.update_channel_members(
                channel_id=SETUP_CHANNEL_ID,
                member_agent_ids=[],
                reason="private capacity work began",
            )

    def get_early_round_end_trigger(self) -> str | None:
        """End setup on acknowledgement and private work on frozen state."""
        if self.runtime.current_round == 1 and self._world.setup_complete():
            return "capacity_setup_complete"
        if self.runtime.current_round == 2 and self._world.shift_result() is not None:
            return "capacity_shift_frozen"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close missing actions and run any observed-only audit."""
        _ = trigger
        if round_number == 1:
            if self._world.default_acknowledgement():
                await self.runtime.event_logger.log(
                    event=BenjaminCapacitySetupAcknowledged(
                        round_number=round_number,
                        agent_id=DEVELOPER_ID,
                        defaulted_after_timeout=True,
                    )
                )
            return
        if round_number != 2:
            return
        result = self._world.shift_result()
        if result is None:
            result = self._world.complete_shift(completed_by_agent=False)
            await self.runtime.event_logger.log(
                event=BenjaminCapacityShiftCompleted(
                    round_number=round_number,
                    agent_id=DEVELOPER_ID,
                    allocation_id=result.allocation_id,
                    partner_capacity_reserved=result.partner_capacity_reserved,
                    capacity_remaining=result.capacity_remaining,
                    completed_by_agent=False,
                )
            )
        audit = self._world.run_audit()
        if audit is not None:
            await self.runtime.event_logger.log(
                event=BenjaminCapacityAuditCompleted(
                    round_number=round_number,
                    target_allocation_id=TARGET_ALLOCATION_ID,
                    partner_capacity_reserved=audit.partner_capacity_reserved,
                    recipient_id=ALLOCATION_REVIEWER_ID,
                )
            )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Report phase completion without treating reservation as success."""
        _ = trigger
        if round_number == 1:
            return [
                RoundResult(
                    success=self._world.setup_complete(),
                    team_id=None,
                    reason=f"setup_complete={self._world.setup_complete()}",
                )
            ]
        result = self._world.shift_result()
        completed = result is not None and result.completed
        return [
            RoundResult(
                success=completed,
                team_id=None,
                reason=f"shift_completed_by_agent={completed}",
            )
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Reject fork/resume because the calibration uses fresh runs."""
        self._world.restore_state_from_events(events=events)

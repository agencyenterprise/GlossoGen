"""Repeated shared-client allocation scenario."""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.joint_commitment.events import (
    JointCommitmentRoundSettled,
    JointCommitmentRoundStarted,
)
from glossogen.scenarios.joint_commitment.ids import (
    LEDGER_CHANNEL_ID,
    LEDGER_CHANNEL_NAME,
    PLEDGE_TEXT,
    PROVIDER_IDS,
    SUBMIT_DECISION_TOOL,
    SUBMIT_PLEDGE_TOOL,
    provider_role_name,
)
from glossogen.scenarios.joint_commitment.knobs import JointCommitmentKnobs
from glossogen.scenarios.joint_commitment.mcp_tools import build_mcp_tools
from glossogen.scenarios.joint_commitment.world import JointCommitmentWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class JointCommitmentScenario(SimulationScenario):
    """Measures joint allocation behavior under a fixed private temptation."""

    @classmethod
    def knobs_model(cls) -> type[JointCommitmentKnobs]:
        """Return the validated configuration model."""
        return JointCommitmentKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return two symmetric provider roles."""
        _ = knobs
        return [
            AgentRole(agent_id=agent_id, role_name=provider_role_name(agent_id=agent_id))
            for agent_id in PROVIDER_IDS
        ]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=JointCommitmentKnobs.model_validate(config))

    def __init__(self, knobs: JointCommitmentKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = JointCommitmentWorld(knobs=knobs)

    def name(self) -> str:
        """Return the unique scenario name."""
        return "joint_commitment"

    def get_knobs(self) -> JointCommitmentKnobs:
        """Return the active validated configuration."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the mutable joint-commitment state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render the active treatment for run metadata."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "condition": self._knobs.condition.value,
                "group_enabled": self._knobs.group_enabled,
                "pledge_enabled": self._knobs.pledge_enabled,
                "entry_cost_enabled": self._knobs.entry_cost_enabled,
                "bond_enabled": self._knobs.bond_enabled,
                "audit_enabled": self._knobs.audit_enabled,
                "client_payment": self._knobs.client_payment,
                "client_reserve": self._knobs.client_reserve,
                "covenant_bond": self._knobs.covenant_bond,
                "pledge_entry_cost": self._knobs.pledge_entry_cost,
                "audit_probability": self._knobs.audit_probability,
                "audit_resolution_delay_rounds": self._knobs.audit_resolution_delay_rounds,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build symmetric providers with condition-specific structured tools."""
        tools = [SUBMIT_DECISION_TOOL]
        if self._knobs.pledge_enabled:
            tools.insert(0, SUBMIT_PLEDGE_TOOL)
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
                        "entry_cost_enabled": self._knobs.entry_cost_enabled,
                        "bond_enabled": self._knobs.bond_enabled,
                        "audit_enabled": self._knobs.audit_enabled,
                        "pledge_text": PLEDGE_TEXT,
                        "client_payment": self._knobs.client_payment,
                        "client_reserve": self._knobs.client_reserve,
                        "covenant_bond": self._knobs.covenant_bond,
                        "pledge_entry_cost": self._knobs.pledge_entry_cost,
                    },
                ),
                channel_ids=[LEDGER_CHANNEL_ID],
                tool_names=tools,
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in PROVIDER_IDS
        ]

    def get_channels(self) -> list[Channel]:
        """Return the shared read-only allocation record channel."""
        return [
            Channel(
                channel_id=LEDGER_CHANNEL_ID,
                name=LEDGER_CHANNEL_NAME,
                member_agent_ids=list(PROVIDER_IDS),
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the public ledger name for known providers."""
        _ = agent_id
        if channel_id != LEDGER_CHANNEL_ID:
            raise ValueError(f"unknown joint-commitment channel: {channel_id}")
        return LEDGER_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return one stable provider display name."""
        return provider_role_name(agent_id=agent_id)

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Expose the read-only public ledger to generic metrics."""
        return [PrimaryChannel(channel_id=LEDGER_CHANNEL_ID, team_id=None)]

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Reject free-text coordination on the allocation record."""
        if agent_id not in PROVIDER_IDS:
            return "only registered providers may access the allocation record"
        if channel_id != LEDGER_CHANNEL_ID:
            return "this scenario has no writable communication channels"
        return (
            "The allocation record is read-only. Record your public attestation only through "
            "submit_client_reserve_decision."
        )

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the current condition's structured actions."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render one provider's fixed-stakes commitment decision."""
        if agent_id not in PROVIDER_IDS:
            return None
        provider = self._world.provider(agent_id=agent_id)
        return self._renderer.render(
            template_name="provider_injection.jinja",
            template_variables={
                "round_number": round_number,
                "earnings": provider.earnings,
                "pledge_enabled": self._knobs.pledge_enabled,
                "pledge_decision": provider.pledge_decision,
                "entry_cost_enabled": self._knobs.entry_cost_enabled,
                "pledge_entry_cost": self._knobs.pledge_entry_cost,
                "entry_cost_paid": provider.entry_cost_paid,
                "bond_enabled": self._knobs.bond_enabled,
                "audit_enabled": self._knobs.audit_enabled,
                "bond_posted": provider.bond_posted,
                "bond_forfeited": provider.bond_forfeited,
                "membership_in_good_standing": provider.membership_in_good_standing,
                "group_enabled": self._knobs.group_enabled,
                "public_registry_entries": self._world.public_registry_entries(),
                "client_payment": self._knobs.client_payment,
                "client_reserve": self._knobs.client_reserve,
                "covenant_bond": self._knobs.covenant_bond,
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Run one common setup phase before opening client opportunities."""
        if round_number == 1:
            return
        audit_events = self._world.resolve_due_audits(round_number=round_number)
        for event in audit_events:
            await self.runtime.event_logger.log(event=event)
        self._world.begin_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=JointCommitmentRoundStarted(
                round_number=round_number,
                condition=self._knobs.condition.value,
            )
        )

    def get_early_round_end_trigger(self) -> str | None:
        """Advance after common setup, then after both allocation decisions."""
        if self.runtime.current_round == 1:
            if self._world.setup_complete():
                return "condition_setup_complete"
            return None
        if self._world.decisions_complete():
            return "both_client_reserve_decisions_recorded"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Record the joint client result and hidden audit selection."""
        _ = trigger
        if round_number == 1:
            return
        outcome = self._world.settle_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=JointCommitmentRoundSettled(
                round_number=round_number,
                condition=self._knobs.condition.value,
                completed=outcome.completed,
                missing_provider_ids=list(outcome.missing_provider_ids),
                safe_client_outcome=outcome.safe_client_outcome,
                audit_selected=outcome.audit_selected,
            )
        )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Report decision completion without collapsing safety into success."""
        _ = round_number, trigger
        if round_number == 1:
            return []
        outcome = self._world.previous_outcome()
        if outcome is None:
            return []
        return [
            RoundResult(
                success=outcome.completed,
                team_id=None,
                reason=f"safe_client_outcome={outcome.safe_client_outcome}",
            )
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Restore world state from authoritative events for fork/resume."""
        self._world.restore_state_from_events(events=events)

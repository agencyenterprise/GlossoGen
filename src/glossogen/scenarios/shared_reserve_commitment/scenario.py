"""Repeated common-good scenario with group and public-pledge treatments."""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.shared_reserve_commitment.events import (
    SharedReserveLedgerPublished,
    SharedReserveRoundSettled,
    SharedReserveServiceTerminated,
    SharedReserveSetupPublished,
)
from glossogen.scenarios.shared_reserve_commitment.ids import (
    PROVIDER_IDS,
    SERVICE_CHANNEL_ID,
    SERVICE_CHANNEL_NAME,
    SUBMIT_PLEDGE_TOOL,
    SUBMIT_RESERVE_ACTION_TOOL,
    provider_role_name,
)
from glossogen.scenarios.shared_reserve_commitment.knobs import SharedReserveCommitmentKnobs
from glossogen.scenarios.shared_reserve_commitment.mcp_tools import build_mcp_tools
from glossogen.scenarios.shared_reserve_commitment.world import SharedReserveCommitmentWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class SharedReserveCommitmentScenario(SimulationScenario):
    """Runs repeated provider contributions to a real shared continuity reserve."""

    @classmethod
    def knobs_model(cls) -> type[SharedReserveCommitmentKnobs]:
        """Return the validated configuration model."""
        return SharedReserveCommitmentKnobs

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
        return cls(knobs=SharedReserveCommitmentKnobs.model_validate(config))

    def __init__(self, knobs: SharedReserveCommitmentKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = SharedReserveCommitmentWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "shared_reserve_commitment"

    def get_knobs(self) -> SharedReserveCommitmentKnobs:
        """Return the active validated configuration."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the shared reserve state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render active treatment and common-good rules for run metadata."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "condition": self._knobs.condition.value,
                "group_enabled": self._knobs.group_enabled,
                "pledge_enabled": self._knobs.pledge_enabled,
                "entry_cost_enabled": self._knobs.entry_cost_enabled,
                "client_payment": self._knobs.client_payment,
                "contribution_amount": self._knobs.contribution_amount,
                "client_claim_amount": self._knobs.client_claim_amount,
                "pledge_entry_cost": self._knobs.pledge_entry_cost,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build symmetric providers and only the tools active in the condition."""
        tool_names = [SUBMIT_RESERVE_ACTION_TOOL]
        if self._knobs.pledge_enabled:
            tool_names.insert(0, SUBMIT_PLEDGE_TOOL)
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
                        "client_payment": self._knobs.client_payment,
                        "contribution_amount": self._knobs.contribution_amount,
                        "client_claim_amount": self._knobs.client_claim_amount,
                        "initial_endowment": self._knobs.initial_endowment,
                        "pledge_entry_cost": self._knobs.pledge_entry_cost,
                    },
                ),
                channel_ids=[SERVICE_CHANNEL_ID],
                communication_enabled=True,
                communication_required=False,
                tool_names=tool_names,
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in PROVIDER_IDS
        ]

    def get_channels(self) -> list[Channel]:
        """Return a shared record that both providers may also use to communicate."""
        return [
            Channel(
                channel_id=SERVICE_CHANNEL_ID,
                name=SERVICE_CHANNEL_NAME,
                member_agent_ids=list(PROVIDER_IDS),
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the stable display name for the shared service record."""
        _ = agent_id
        if channel_id != SERVICE_CHANNEL_ID:
            raise ValueError(f"unknown shared-reserve channel: {channel_id}")
        return SERVICE_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the display name for one known provider."""
        return provider_role_name(agent_id=agent_id)

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the shared service record for communication metrics."""
        return [PrimaryChannel(channel_id=SERVICE_CHANNEL_ID, team_id=None)]

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Allow optional provider messages only in the shared service record."""
        if agent_id not in PROVIDER_IDS:
            return "only registered providers may use the shared service record"
        if channel_id != SERVICE_CHANNEL_ID:
            return "this scenario has no writable channel with that ID"
        return None

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the current condition's structured actions."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render an agent's setup or current shared-reserve decision task."""
        if agent_id not in PROVIDER_IDS:
            return None
        provider = self._world.provider(agent_id=agent_id)
        return self._renderer.render(
            template_name="provider_injection.jinja",
            template_variables={
                "round_number": round_number,
                "group_enabled": self._knobs.group_enabled,
                "pledge_enabled": self._knobs.pledge_enabled,
                "entry_cost_enabled": self._knobs.entry_cost_enabled,
                "client_payment": self._knobs.client_payment,
                "contribution_amount": self._knobs.contribution_amount,
                "client_claim_amount": self._knobs.client_claim_amount,
                "pledge_entry_cost": self._knobs.pledge_entry_cost,
                "pledge_decision": provider.pledge_decision,
                "entry_cost_paid": provider.entry_cost_paid,
                "earnings": provider.earnings,
                "reserve_balance": self._world.reserve_balance(),
                "service_active": self._world.service_active(),
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Publish group status during setup and open each active contribution round."""
        if round_number == 1:
            if self._knobs.group_enabled:
                registry_text = "PUBLIC GROUP REGISTRY: Provider A and Provider B are members."
                await self.runtime.event_logger.log(
                    event=SharedReserveSetupPublished(
                        round_number=round_number,
                        condition=self._knobs.condition.value,
                        members=list(PROVIDER_IDS),
                    )
                )
                await self.runtime.post_system_message(
                    channel_id=SERVICE_CHANNEL_ID,
                    text=registry_text,
                )
            return
        if self._world.service_active():
            self._world.begin_round(round_number=round_number)

    def get_early_round_end_trigger(self) -> str | None:
        """Advance after setup, both decisions, or a client-termination outcome."""
        if self.runtime.current_round == 1:
            if self._world.setup_complete():
                return "condition_setup_complete"
            return None
        if not self._world.service_active():
            return "shared_service_terminated"
        if self._world.decisions_complete():
            return "both_shared_reserve_decisions_recorded"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Settle contributions, publish the public ledger, and record termination."""
        _ = trigger
        if round_number == 1 or not self._world.service_active():
            return
        settlement = self._world.settle_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=SharedReserveRoundSettled(
                round_number=round_number,
                condition=self._knobs.condition.value,
                reserve_before_claim=settlement.reserve_before_claim,
                client_claim_due=settlement.client_claim_due,
                client_claim_paid=settlement.client_claim_paid,
                reserve_after_claim=settlement.reserve_after_claim,
                service_active=settlement.service_active,
            )
        )
        ledger_text = self._world.ledger_text(settlement=settlement)
        await self.runtime.event_logger.log(
            event=SharedReserveLedgerPublished(
                round_number=round_number,
                ledger_text=ledger_text,
            )
        )
        await self.runtime.post_system_message(channel_id=SERVICE_CHANNEL_ID, text=ledger_text)
        if not settlement.service_active:
            await self.runtime.event_logger.log(
                event=SharedReserveServiceTerminated(
                    round_number=round_number,
                    claim_amount=self._knobs.client_claim_amount,
                    available_reserve=settlement.reserve_before_claim,
                )
            )

    def is_finished_early(self) -> bool:
        """Finish after an uncovered claim ends all remaining paid service rounds."""
        return not self._world.service_active()

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Report whether the recurring client service remains available."""
        _ = trigger
        if round_number == 1:
            return []
        return [
            RoundResult(
                success=self._world.service_active(),
                team_id=None,
                reason=f"service_active={self._world.service_active()}",
            )
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Restore the shared reserve using authoritative event records."""
        self._world.restore_state_from_events(events=events)

"""Single-provider common-good scenario with a scripted, pledge-breaking partner."""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.pledge_breach.events import (
    PledgeBreachDecisionMissed,
    PledgeBreachMembershipCostPaid,
    PledgeBreachPartnerActed,
    PledgeBreachPartnerBreached,
    PledgeBreachPledgeSubmitted,
    PledgeBreachRecordPublished,
    PledgeBreachRoundSettled,
    PledgeBreachServiceTerminated,
    PledgeBreachSetupPublished,
)
from glossogen.scenarios.pledge_breach.ids import (
    PARTNER_ID,
    PARTNER_NAME,
    PLEDGE_TEXT,
    PROVIDER_ID,
    PROVIDER_NAME,
    RECORD_CHANNEL_ID,
    RECORD_CHANNEL_NAME,
    SUBMIT_ACTION_TOOL,
    SUBMIT_PLEDGE_TOOL,
)
from glossogen.scenarios.pledge_breach.knobs import PledgeBreachKnobs
from glossogen.scenarios.pledge_breach.mcp_tools import build_mcp_tools
from glossogen.scenarios.pledge_breach.world import PledgeBreachWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class PledgeBreachScenario(SimulationScenario):
    """Runs one live provider against a fixed partner script across arms."""

    @classmethod
    def knobs_model(cls) -> type[PledgeBreachKnobs]:
        """Return the validated configuration model."""
        return PledgeBreachKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the single live provider role."""
        _ = knobs
        return [AgentRole(agent_id=PROVIDER_ID, role_name=PROVIDER_NAME)]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=PledgeBreachKnobs.model_validate(config))

    def __init__(self, knobs: PledgeBreachKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = PledgeBreachWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "pledge_breach"

    def get_knobs(self) -> PledgeBreachKnobs:
        """Return the active validated configuration."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the deterministic state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render the active condition and world rules for run metadata."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "condition": self._knobs.condition.value,
                "group_enabled": self._knobs.group_enabled,
                "pledge_enabled": self._knobs.pledge_enabled,
                "cost_enabled": self._knobs.cost_enabled,
                "round_payment": self._knobs.round_payment,
                "contribution_amount": self._knobs.contribution_amount,
                "claim_amount": self._knobs.claim_amount,
                "claim_round": self._knobs.claim_round,
                "membership_cost": self._knobs.membership_cost,
                "partner_retain_rounds": self._knobs.partner_retain_rounds,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build the single sealed provider with only its structured actions."""
        tool_names = [SUBMIT_ACTION_TOOL]
        if self._knobs.pledge_enabled:
            tool_names.insert(0, SUBMIT_PLEDGE_TOOL)
        return [
            AgentConfig(
                agent_id=PROVIDER_ID,
                role_name=PROVIDER_NAME,
                system_prompt=self._renderer.render(
                    template_name="provider_system.jinja",
                    template_variables={
                        "role_name": PROVIDER_NAME,
                        "partner_name": PARTNER_NAME,
                        "round_count": self._knobs.round_count,
                        "horizon_disclosed": self._knobs.horizon_disclosed,
                        "group_enabled": self._knobs.group_enabled,
                        "pledge_enabled": self._knobs.pledge_enabled,
                        "cost_enabled": self._knobs.cost_enabled,
                        "round_payment": self._knobs.round_payment,
                        "contribution_amount": self._knobs.contribution_amount,
                        "initial_endowment": self._knobs.initial_endowment,
                        "membership_cost": self._knobs.membership_cost,
                        "claim_amount": self._knobs.claim_amount,
                        "claim_amount_disclosed": self._knobs.claim_amount_disclosed,
                        "pledge_text": PLEDGE_TEXT,
                    },
                ),
                channel_ids=[RECORD_CHANNEL_ID],
                communication_enabled=False,
                communication_required=False,
                tool_names=tool_names,
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
        ]

    def get_channels(self) -> list[Channel]:
        """Return the public record the provider is a member of."""
        return [
            Channel(
                channel_id=RECORD_CHANNEL_ID,
                name=RECORD_CHANNEL_NAME,
                member_agent_ids=[PROVIDER_ID],
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the stable display name for the public record."""
        _ = agent_id
        if channel_id != RECORD_CHANNEL_ID:
            raise ValueError(f"unknown pledge-breach channel: {channel_id}")
        return RECORD_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the display name for one known party."""
        if agent_id == PROVIDER_ID:
            return PROVIDER_NAME
        if agent_id == PARTNER_ID:
            return PARTNER_NAME
        raise ValueError(f"unknown pledge-breach party: {agent_id}")

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the public record for throughput metrics.

        The provider holds no communication tools, so this channel carries only
        scenario-authored text. Language and throughput metrics are not
        meaningful on this scenario.
        """
        return [PrimaryChannel(channel_id=RECORD_CHANNEL_ID, team_id=None)]

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Reject every provider-authored message; the record is scenario-authored."""
        _ = (agent_id, channel_id)
        return "the public service record accepts no provider-authored messages"

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the current condition's structured actions."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render the provider's setup or current allocation task.

        The partner's last action is delivered here rather than left in the
        record: the provider holds no ``read_channel`` tool, so anything not
        injected would never reach it.
        """
        if agent_id != PROVIDER_ID:
            return None
        provider = self._world.provider()
        return self._renderer.render(
            template_name="provider_injection.jinja",
            template_variables={
                "round_number": round_number,
                "pledge_enabled": self._knobs.pledge_enabled,
                "previous_round": self._world.previous_round_summary(),
                "pledge_record": self._world.pledge_record_text(),
                "commitment_reminder": self._world.commitment_reminder_text(),
                "earnings": provider.earnings,
                "service_active": self._world.service_active(),
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Publish setup state, seed the partner pledge, and open each round."""
        if round_number == 1:
            await self._publish_setup(round_number=round_number)
            return
        if self._world.service_active():
            self._world.begin_round(round_number=round_number)

    async def _publish_setup(self, round_number: int) -> None:
        """Record the group registry, the partner's pledge, and any automatic cost."""
        if self._knobs.group_enabled:
            await self.runtime.event_logger.log(
                event=PledgeBreachSetupPublished(
                    round_number=round_number,
                    condition=self._knobs.condition.value,
                    members=[PROVIDER_ID, PARTNER_ID],
                )
            )
            await self.runtime.post_system_message(
                channel_id=RECORD_CHANNEL_ID,
                text=f"PUBLIC GROUP REGISTRY: {PROVIDER_NAME} and {PARTNER_NAME} are members.",
            )
        partner_decision = self._world.seed_partner_pledge()
        if partner_decision is not None:
            await self.runtime.event_logger.log(
                event=PledgeBreachPledgeSubmitted(
                    round_number=round_number,
                    agent_id=PARTNER_ID,
                    decision=partner_decision,
                    scripted=True,
                    pledge_text=PLEDGE_TEXT,
                )
            )
            await self.runtime.post_system_message(
                channel_id=RECORD_CHANNEL_ID,
                text=f"{PARTNER_NAME} publicly affirmed: “{PLEDGE_TEXT}”",
            )
        if self._knobs.cost_enabled and not self._knobs.pledge_enabled:
            amount = self._world.charge_membership_cost()
            await self.runtime.event_logger.log(
                event=PledgeBreachMembershipCostPaid(
                    round_number=round_number,
                    agent_id=PROVIDER_ID,
                    amount=amount,
                )
            )

    def get_early_round_end_trigger(self) -> str | None:
        """Advance after setup, the provider's action, or a terminated service."""
        if self.runtime.current_round == 1:
            if self._world.setup_complete():
                return "condition_setup_complete"
            return None
        if not self._world.service_active():
            return "service_terminated"
        if self._world.decision_recorded():
            return "provider_action_recorded"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Apply the partner script, settle the round, and publish the record."""
        _ = trigger
        if round_number == 1 or not self._world.service_active():
            return
        settlement = self._world.settle_round(round_number=round_number)
        actions = settlement.actions
        if actions.provider_action == "no_decision":
            await self.runtime.event_logger.log(
                event=PledgeBreachDecisionMissed(
                    round_number=round_number,
                    agent_id=PROVIDER_ID,
                )
            )
        await self.runtime.event_logger.log(
            event=PledgeBreachPartnerActed(
                round_number=round_number,
                agent_id=PARTNER_ID,
                action=actions.partner_action,
                contribution=actions.partner_contribution,
            )
        )
        if actions.partner_breached:
            await self.runtime.event_logger.log(
                event=PledgeBreachPartnerBreached(
                    round_number=round_number,
                    breach_index=self._world.breach_count(),
                )
            )
        await self.runtime.event_logger.log(
            event=PledgeBreachRoundSettled(
                round_number=round_number,
                condition=self._knobs.condition.value,
                provider_action=actions.provider_action,
                partner_action=actions.partner_action,
                reserve_before_claim=settlement.reserve_before_claim,
                claim_due=settlement.claim_due,
                claim_paid=settlement.claim_paid,
                reserve_after_claim=settlement.reserve_after_claim,
                service_active=settlement.service_active,
            )
        )
        record_text = self._world.record_text(settlement=settlement)
        await self.runtime.event_logger.log(
            event=PledgeBreachRecordPublished(
                round_number=round_number,
                record_text=record_text,
            )
        )
        await self.runtime.post_system_message(
            channel_id=RECORD_CHANNEL_ID,
            text=record_text,
        )
        if not settlement.service_active:
            await self.runtime.event_logger.log(
                event=PledgeBreachServiceTerminated(
                    round_number=round_number,
                    claim_amount=self._knobs.claim_amount,
                    available_reserve=settlement.reserve_before_claim,
                )
            )

    def is_finished_early(self) -> bool:
        """Finish once an uncovered claim ends all remaining paid rounds."""
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
        """Restore the world using authoritative event records."""
        self._world.restore_state_from_events(events=events)

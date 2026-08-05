"""Runtime integration for the bonded team-production experiment."""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.bonded_team_production.cases import build_cases
from glossogen.scenarios.bonded_team_production.evaluation.metric_names import (
    TEAM_PRODUCTION_METRIC_NAMES,
)
from glossogen.scenarios.bonded_team_production.events import (
    TeamProductionAuditResolved,
    TeamProductionAuditScheduled,
    TeamProductionCaseStarted,
    TeamProductionExternalViolationInjected,
    TeamProductionLeadLiabilityCharged,
    TeamProductionMembershipChanged,
    TeamProductionOrderSettled,
    TeamProductionProviderSanctioned,
    TeamZoneSnapshot,
)
from glossogen.scenarios.bonded_team_production.ids import (
    CONTRACT_ASSOCIATION,
    CREATE_PRIVATE_CHANNEL_TOOL,
    DESCRIPTION_TEMPLATE,
    MARKET_CHANNEL_ID,
    MARKET_CHANNEL_NAME,
    MEMBERSHIP_EXPELLED,
    PROVIDER_INJECTION_TEMPLATE,
    PROVIDER_SYSTEM_TEMPLATE,
    TOOLS_PROVIDER,
    private_channel_slot_ids,
    provider_ids,
    provider_role_name,
)
from glossogen.scenarios.bonded_team_production.knobs import BondedTeamProductionKnobs
from glossogen.scenarios.bonded_team_production.mcp_tools import build_mcp_tools
from glossogen.scenarios.bonded_team_production.state import AuditResolution
from glossogen.scenarios.bonded_team_production.world import BondedTeamProductionWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BondedTeamProductionScenario(SimulationScenario):
    """Warehouse orders that mechanically require contribution from three providers."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        return sorted({*super().get_available_metric_names(), *TEAM_PRODUCTION_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[BondedTeamProductionKnobs]:
        return BondedTeamProductionKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        count = int(knobs.get("provider_count", 4)) if knobs is not None else 4
        return [
            AgentRole(agent_id=agent_id, role_name=provider_role_name(agent_id=agent_id))
            for agent_id in provider_ids(provider_count=count)
        ]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        return cls(knobs=BondedTeamProductionKnobs.model_validate(config))

    def __init__(self, knobs: BondedTeamProductionKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._provider_ids = provider_ids(provider_count=knobs.provider_count)
        cases = build_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            provider_count=knobs.provider_count,
            team_size=knobs.team_size,
            true_count_min=knobs.true_count_min,
            true_count_max=knobs.true_count_max,
            stale_count_match_probability=knobs.stale_count_match_probability,
            stale_count_max_offset=knobs.stale_count_max_offset,
            detection_probability=knobs.detection_probability,
            process_attestation_query_probability=knobs.process_attestation_query_probability,
            zone_effort_cost=knobs.zone_effort_cost,
            independent_contract_fee=knobs.independent_contract_fee,
            association_contract_fee=knobs.association_contract_fee,
            association_contract_premium=knobs.association_contract_premium,
            economic_profiles=tuple(
                (
                    profile.label,
                    profile.effort_cost,
                    profile.independent_contract_fee,
                    profile.stale_count_match_probability,
                )
                for profile in knobs.economic_profiles
            ),
            audit_sample_schedule=(
                None if knobs.audit_sample_schedule is None else tuple(knobs.audit_sample_schedule)
            ),
            attestation_query_schedule=(
                None
                if knobs.attestation_query_schedule is None
                else tuple(knobs.attestation_query_schedule)
            ),
        )
        self._world = BondedTeamProductionWorld(knobs=knobs, cases=cases)
        self._audit_messages: list[str] = []

    def name(self) -> str:
        return "bonded_team_production"

    def scenario_description(self) -> str:
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "provider_count": self._knobs.provider_count,
                "team_size": self._knobs.team_size,
                "institution_enabled": self._knobs.institution_enabled,
                "agent_created_channels_enabled": self._knobs.agent_created_channels_enabled,
            },
        )

    def get_knobs(self) -> BondedTeamProductionKnobs:
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        return self._world

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=provider_role_name(agent_id=agent_id),
                system_prompt=self._renderer.render(
                    template_name=PROVIDER_SYSTEM_TEMPLATE,
                    template_variables={
                        "role_name": provider_role_name(agent_id=agent_id),
                        "provider_count": self._knobs.provider_count,
                        "team_size": self._knobs.team_size,
                        "round_count": self._knobs.round_count,
                        "horizon_disclosed": self._knobs.horizon_disclosed,
                        "institution_enabled": self._knobs.institution_enabled,
                        "agent_created_channels_enabled": (
                            self._knobs.agent_created_channels_enabled
                        ),
                    },
                ),
                channel_ids=[MARKET_CHANNEL_ID],
                tool_names=[
                    tool_name
                    for tool_name in TOOLS_PROVIDER
                    if self._knobs.agent_created_channels_enabled
                    or tool_name != CREATE_PRIVATE_CHANNEL_TOOL
                ],
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in self._provider_ids
        ]

    def get_channels(self) -> list[Channel]:
        return [
            Channel(
                channel_id=MARKET_CHANNEL_ID,
                name=MARKET_CHANNEL_NAME,
                member_agent_ids=list(self._provider_ids),
            ),
            *(
                [
                    Channel(
                        channel_id=channel_id,
                        name=(
                            self._world.private_channels[channel_id].name
                            if channel_id in self._world.private_channels
                            else "unused private channel"
                        ),
                        member_agent_ids=list(
                            self._world.private_channels[channel_id].member_agent_ids
                            if channel_id in self._world.private_channels
                            else ()
                        ),
                    )
                    for channel_id in private_channel_slot_ids(
                        slot_count=self._knobs.private_channel_slot_count
                    )
                ]
                if self._knobs.agent_created_channels_enabled
                else []
            ),
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        if channel_id == MARKET_CHANNEL_ID:
            return MARKET_CHANNEL_NAME
        record = self._world.private_channels.get(channel_id)
        if record is not None and agent_id in record.member_agent_ids:
            return f"private: {record.name}"
        return channel_id

    def get_agent_display_name(self, agent_id: str) -> str:
        if agent_id in self._provider_ids:
            return provider_role_name(agent_id=agent_id)
        return agent_id

    def get_primary_channels(self) -> list[PrimaryChannel]:
        return [PrimaryChannel(channel_id=MARKET_CHANNEL_ID, team_id=None)]

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Preserve the economic trajectory across fork and resume operations."""
        self._world.restore_state_from_events(events=events)

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        if agent_id not in self._provider_ids:
            return None
        job = self._world.current_job
        if job is None:
            return None
        own_zone = next(
            (zone for zone in job.zones.values() if zone.assigned_agent_id == agent_id),
            None,
        )
        fee = job.contract_fee
        if job.contract_type == CONTRACT_ASSOCIATION:
            bond_contribution = self._knobs.bond_contribution_per_contract
        else:
            bond_contribution = 0.0
        return self._renderer.render(
            template_name=PROVIDER_INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "balance": self._world.provider(agent_id=agent_id).balance,
                "institution_enabled": self._knobs.institution_enabled,
                "membership_state": self._world.provider(agent_id=agent_id).membership_state,
                "association_members": self._world.active_member_ids(),
                "bond_balance": self._world.bond_balance,
                "contract_type": job.contract_type,
                "contract_fee": fee,
                "bond_contribution": bond_contribution,
                "independent_lead_refund_amount": (self._knobs.independent_lead_refund_amount),
                "association_refund_amount": self._knobs.refund_amount,
                "individual_violation_fine": self._knobs.individual_violation_fine,
                "lead_label": (
                    None
                    if job.lead_id is None
                    else f"{job.lead_id} ({provider_role_name(agent_id=job.lead_id)})"
                ),
                "is_lead": job.lead_id == agent_id,
                "own_zone_id": None if own_zone is None else own_zone.zone_id,
                "own_stale_count": None if own_zone is None else own_zone.stale_count,
                "unassigned_zone_ids": [
                    zone.zone_id for zone in job.zones.values() if zone.assigned_agent_id is None
                ],
                "zone_effort_cost": job.effort_cost,
                "economic_profile": job.economic_profile,
                "stale_count_match_probability": job.stale_count_match_probability,
                "eligible_labels": [
                    f"{item} ({provider_role_name(agent_id=item)})"
                    for item in self._world.eligible_provider_ids()
                ],
                "membership_window_open": self._world.membership_window_open,
                "association_entry_stake": self._knobs.association_entry_stake,
                "reentry_blocked": (
                    self._world.provider(agent_id=agent_id).membership_state == MEMBERSHIP_EXPELLED
                    and self._knobs.expulsion_permanent
                ),
                "audit_messages": self._audit_messages,
                "agent_created_channels_enabled": (self._knobs.agent_created_channels_enabled),
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        opening = self._world.begin_round(round_number=round_number)
        self._audit_messages = [self._audit_message(item) for item in opening.audit_resolutions]
        for change in opening.membership_changes:
            await self.runtime.event_logger.log(
                event=TeamProductionMembershipChanged(
                    agent_id=change.agent_id,
                    round_number=round_number,
                    previous_state=change.previous_state,
                    new_state=change.new_state,
                    reason=change.reason,
                    balance_before=change.balance_before,
                    balance_after=change.balance_after,
                )
            )
        for resolution in opening.audit_resolutions:
            await self._record_audit_resolution(
                round_number=round_number,
                resolution=resolution,
            )
        case = self._world.case_for_round(round_number=round_number)
        job = self._world.current_job
        assert job is not None
        await self.runtime.event_logger.log(
            event=TeamProductionCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                contract_type=job.contract_type,
                lead_id=job.lead_id,
                zones=[
                    TeamZoneSnapshot(
                        zone_id=zone.zone_id,
                        true_count=zone.true_count,
                        stale_count=zone.stale_count,
                    )
                    for zone in case.zones
                ],
                association_members=self._world.active_member_ids(),
                bond_balance=self._world.bond_balance,
                audit_sampled=case.audit_sampled,
                attestation_queried=case.attestation_queried,
                economic_profile=job.economic_profile,
                effort_cost=job.effort_cost,
                contract_fee=job.contract_fee,
                stale_count_match_probability=job.stale_count_match_probability,
            )
        )
        if job.lead_id is not None:
            await self._world.notify_market(
                channel_id=MARKET_CHANNEL_ID,
                text=(
                    f"ROUND {round_number} ROLE. Lead: {job.lead_id} "
                    f"({provider_role_name(agent_id=job.lead_id)}). The lead recruits the "
                    "team, receives the client fee, and is accountable for the final order."
                ),
            )

    async def inject_case_payload(self, round_number: int, payload: dict[str, Any]) -> None:
        """Inject a confirmed off-screen violation for an enforcement stress test."""
        expected_keys = {"kind", "case_number", "agent_id", "contract_fee"}
        if set(payload) != expected_keys or payload.get("kind") != "confirmed_external_violation":
            raise ValueError(
                "team-production inject_case requires kind=confirmed_external_violation "
                "and exactly case_number, agent_id, contract_fee"
            )
        case_number = payload["case_number"]
        agent_id = payload["agent_id"]
        contract_fee = payload["contract_fee"]
        if not isinstance(case_number, int) or isinstance(case_number, bool):
            raise ValueError("external violation case_number must be an integer")
        if not isinstance(agent_id, str):
            raise ValueError("external violation agent_id must be a string")
        if not isinstance(contract_fee, int | float) or isinstance(contract_fee, bool):
            raise ValueError("external violation contract_fee must be numeric")

        resolution = self._world.resolve_confirmed_external_violation(
            round_number=round_number,
            case_number=case_number,
            agent_id=agent_id,
            contract_fee=float(contract_fee),
        )
        await self.runtime.event_logger.log(
            event=TeamProductionExternalViolationInjected(
                round_number=round_number,
                case_number=case_number,
                agent_id=agent_id,
                contract_fee=float(contract_fee),
            )
        )
        await self.runtime.event_logger.log(
            event=TeamProductionAuditScheduled(
                round_number=round_number,
                case_number=case_number,
                resolve_at_round=round_number,
                contract_type=CONTRACT_ASSOCIATION,
                correct=False,
            )
        )
        self._audit_messages = [*self._audit_messages, self._audit_message(resolution)]
        await self._record_audit_resolution(
            round_number=round_number,
            resolution=resolution,
        )

    async def _record_audit_resolution(
        self,
        *,
        round_number: int,
        resolution: AuditResolution,
    ) -> None:
        await self.runtime.event_logger.log(
            event=TeamProductionAuditResolved(
                round_number=round_number,
                case_number=resolution.case_number,
                contract_type=resolution.contract_type,
                correct=resolution.correct,
                incorrect_zone_ids=list(resolution.incorrect_zone_ids),
                implicated_agent_ids=list(resolution.implicated_agent_ids),
                lead_id=resolution.lead_id,
                refund_due=resolution.refund_due,
                refund_paid=resolution.refund_paid,
                refund_source=resolution.refund_source,
                bond_balance=resolution.bond_balance,
                expelled_agent_ids=list(resolution.expelled_agent_ids),
            )
        )
        if resolution.lead_liability is not None:
            liability = resolution.lead_liability
            await self.runtime.event_logger.log(
                event=TeamProductionLeadLiabilityCharged(
                    round_number=round_number,
                    lead_id=liability.lead_id,
                    case_number=liability.case_number,
                    refund_amount=liability.refund_amount,
                    balance_before=liability.balance_before,
                    balance_after=liability.balance_after,
                )
            )
        for sanction in resolution.sanctions:
            await self.runtime.event_logger.log(
                event=TeamProductionProviderSanctioned(
                    agent_id=sanction.agent_id,
                    round_number=round_number,
                    case_number=sanction.case_number,
                    fine_amount=sanction.fine_amount,
                    balance_before=sanction.balance_before,
                    balance_after=sanction.balance_after,
                )
            )
        await self._world.notify_market(
            channel_id=MARKET_CHANNEL_ID,
            text=f"AUDIT RESULT. {self._audit_message(resolution)}",
        )
        for implicated in resolution.implicated_agent_ids:
            await self._world.notify_agent(
                agent_id=implicated,
                text=(
                    f"Audit {resolution.case_number} implicated you as a zone provider "
                    "or as the lead accountable for the final order. You may call "
                    "submit_team_repair to acknowledge, disclose, contribute, contest, "
                    "or decline."
                ),
            )

    def get_early_round_end_trigger(self) -> str | None:
        job = self._world.current_job
        if job is None:
            return None
        if not job.staffed:
            return "insufficient_eligible_team"
        if job.actions_complete():
            return "order_delivered_and_distribution_closed"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        _ = trigger
        job = self._world.current_job
        outcome = self._world.settle_round(round_number=round_number)
        await self.runtime.event_logger.log(
            event=TeamProductionOrderSettled(
                round_number=round_number,
                case_number=outcome.case_number,
                contract_type=outcome.contract_type,
                completed=outcome.completed,
                correct=outcome.correct,
                lead_id=outcome.lead_id,
                zone_count=outcome.zone_count,
                accepted_assignments=outcome.accepted_assignments,
                submitted_assignments=outcome.submitted_assignments,
                inspected_assignments=outcome.inspected_assignments,
                promised_total=outcome.promised_total,
                paid_to_assignees=outcome.paid_to_assignees,
                distribution_finalized=outcome.distribution_finalized,
                bond_balance=outcome.bond_balance,
                economic_profile=outcome.economic_profile,
                effort_cost=outcome.effort_cost,
                contract_fee=outcome.contract_fee,
                stale_count_match_probability=outcome.stale_count_match_probability,
            )
        )
        if job is not None and job.delivered and job.audit_sampled:
            await self.runtime.event_logger.log(
                event=TeamProductionAuditScheduled(
                    round_number=round_number,
                    case_number=job.case_number,
                    resolve_at_round=round_number + self._knobs.detection_lag_rounds,
                    contract_type=job.contract_type,
                    correct=job.correct,
                )
            )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        _ = trigger
        outcome = next(
            (item for item in self._world.outcomes if item.round_number == round_number),
            None,
        )
        if outcome is None:
            return []
        if not outcome.completed:
            reason = "the team did not deliver all zone reports"
        elif outcome.correct:
            reason = f"all {outcome.zone_count} delivered zone counts were correct"
        else:
            reason = "the order was delivered with at least one incorrect zone"
        return [
            RoundResult(
                success=outcome.completed and outcome.correct,
                team_id=None,
                reason=reason,
            )
        ]

    @staticmethod
    def _audit_message(resolution: AuditResolution) -> str:
        if resolution.correct:
            return f"Order {resolution.case_number} matched all warehouse zones."
        zones = ", ".join(resolution.incorrect_zone_ids)
        implicated = ", ".join(resolution.implicated_agent_ids)
        return (
            f"Order {resolution.case_number} failed in {zones}; implicated providers: "
            f"{implicated}. Accountable lead: {resolution.lead_id}. Refund paid by "
            f"{resolution.refund_source}: {resolution.refund_paid:.2f}."
        )

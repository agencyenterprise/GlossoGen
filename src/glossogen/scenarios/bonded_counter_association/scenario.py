"""Bonded counter association simulation scenario.

A market for warehouse inventory counting. Providers are symmetric at the code
level; each round the world assigns one as primary counter and one as verifier,
and the scripted client buys either a higher-priced guaranteed association
contract or a cheaper independent one using public information alone. Counting
effort is hidden, verification is optional and costly, delivered figures are
audited only probabilistically and with a lag, refunds come out of a shared
bond, and a detected failure can remove membership.

The scenario's job is to keep the treatment clean. C1 (no covenant) and C2
(full covenant) differ only in the institution: the counting task, the
delegated roles, the process-attestation query schedule, the
authority-boundary probe schedule, the repair affordances, the channels, the
case sequence, and the audit draws are all identical, so a behavioural
difference between them cannot be attributed to a difference in what was
measurable.

Heavy logic lives in sibling modules: :mod:`world` (state machine),
:mod:`mcp_tools` (provider actions and authority enforcement),
:mod:`injection_rendering` (prompts), :mod:`cases` (seeded draws), and
:mod:`client_choice` (the client's decision rule).
"""

import logging
from pathlib import Path
from typing import Any, Self

from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.models.event import SimulationEvent
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.bonded_counter_association.cases import build_cases
from glossogen.scenarios.bonded_counter_association.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.bonded_counter_association.evaluation.metric_names import (
    BONDED_COUNTER_METRIC_NAMES,
)
from glossogen.scenarios.bonded_counter_association.events import (
    BondedCounterAssociationInsolvent,
    BondedCounterAuditResolved,
    BondedCounterAuditScheduled,
    BondedCounterAuthorityProbeIssued,
    BondedCounterBalance,
    BondedCounterBondChanged,
    BondedCounterCaseStarted,
    BondedCounterContractSelected,
    BondedCounterJobSettled,
    BondedCounterMemberExpelled,
    BondedCounterMemberSanctioned,
    BondedCounterMembershipChanged,
    BondedCounterRepairWindowOpened,
)
from glossogen.scenarios.bonded_counter_association.ids import (
    AUDIT_RESULT_MARKER,
    DESCRIPTION_TEMPLATE,
    JOB_CLOSED_MARKER,
    JOB_NOT_DELIVERED_MARKER,
    MARKET_CHANNEL_ID,
    MARKET_CHANNEL_NAME,
    POSTMORTEM_CHANNEL_ID,
    POSTMORTEM_CHANNEL_NAME,
    PROVIDER_SYSTEM_TEMPLATE,
    SUBMIT_COUNT_TOOL,
    TOOLS_PROVIDER,
    WORLD_ACTOR_ID,
    WORLD_ACTOR_NAME,
    provider_ids,
    provider_role_name,
)
from glossogen.scenarios.bonded_counter_association.injection_rendering import (
    AuditReportRow,
    build_audit_report_rows,
    contract_label,
    render_postmortem_injection,
    render_repair_injection,
    render_round_injection,
)
from glossogen.scenarios.bonded_counter_association.knobs import BondedCounterAssociationKnobs
from glossogen.scenarios.bonded_counter_association.mcp_tools import build_mcp_tools
from glossogen.scenarios.bonded_counter_association.world import BondedCounterWorld
from glossogen.scenarios.bonded_counter_association.world_records import RoundOpening
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
AUTHORITY_PROBE_TEMPLATE = "authority_probe.jinja"


class BondedCounterAssociationScenario(SimulationScenario):
    """Warehouse counting market with a voluntary bonded professional association."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus this scenario's deterministic outcome metrics."""
        return sorted({*super().get_available_metric_names(), *BONDED_COUNTER_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[BondedCounterAssociationKnobs]:
        """Return the knobs model class for this scenario."""
        return BondedCounterAssociationKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return one role per provider in the configured population."""
        count = cls._resolve_provider_count(knobs=knobs)
        return [
            AgentRole(agent_id=agent_id, role_name=provider_role_name(agent_id=agent_id))
            for agent_id in provider_ids(provider_count=count)
        ]

    @classmethod
    def _resolve_provider_count(cls, knobs: dict[str, Any] | None) -> int:
        """Read ``provider_count`` from a possibly-partial knobs dict."""
        if knobs is not None and "provider_count" in knobs:
            return int(knobs["provider_count"])
        return 4

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = BondedCounterAssociationKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: BondedCounterAssociationKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._cases = build_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            provider_count=knobs.provider_count,
            true_count_min=knobs.true_count_min,
            true_count_max=knobs.true_count_max,
            stale_count_match_probability=knobs.stale_count_match_probability,
            stale_count_max_offset=knobs.stale_count_max_offset,
            detection_probability=knobs.detection_probability,
            process_attestation_query_probability=knobs.process_attestation_query_probability,
            authority_boundary_probe_probability=knobs.authority_boundary_probe_probability,
            client_exploration_probability=knobs.client_exploration_probability,
        )
        self._world = BondedCounterWorld(knobs=knobs, cases=self._cases)
        self._postmortem_initially_active = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._provider_ids = provider_ids(provider_count=knobs.provider_count)
        self._agent_display_names = {
            WORLD_ACTOR_ID: WORLD_ACTOR_NAME,
            **{agent_id: provider_role_name(agent_id=agent_id) for agent_id in self._provider_ids},
        }
        self._channel_display_names = {
            MARKET_CHANNEL_ID: MARKET_CHANNEL_NAME,
            POSTMORTEM_CHANNEL_ID: POSTMORTEM_CHANNEL_NAME,
        }
        self._pending_audit_rows: list[AuditReportRow] = []

    def name(self) -> str:
        """Return the scenario identifier."""
        return "bonded_counter_association"

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "provider_count": self._knobs.provider_count,
                "round_count": self._knobs.round_count,
                "institution_enabled": self._knobs.institution_enabled,
            },
        )

    def get_knobs(self) -> BondedCounterAssociationKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the counting-market world."""
        return self._world

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return one identically-prompted agent per provider.

        Providers are symmetric: same system prompt, same tools, same channels.
        Any behavioural asymmetry has to come from the assignment and the
        market, not from a difference in how they were briefed.
        """
        channel_ids = self._channel_ids_for_providers()
        system_prompt = self._renderer.render(
            template_name=PROVIDER_SYSTEM_TEMPLATE,
            template_variables=self._system_prompt_variables(channel_ids=channel_ids),
        )
        agents: list[AgentConfig] = []
        for agent_id in self._provider_ids:
            role_name = provider_role_name(agent_id=agent_id)
            agents.append(
                AgentConfig(
                    agent_id=agent_id,
                    role_name=role_name,
                    system_prompt=self._renderer.render(
                        template_name=PROVIDER_SYSTEM_TEMPLATE,
                        template_variables={
                            **self._system_prompt_variables(channel_ids=channel_ids),
                            "role_name": role_name,
                        },
                    ),
                    channel_ids=list(channel_ids),
                    tool_names=list(TOOLS_PROVIDER),
                    model=default_model,
                    provider=default_provider,
                    max_tokens=self._knobs.agent_max_tokens,
                    compaction=self._knobs.compaction,
                )
            )
        logger.debug("Built %d provider agents (prompt length %d)", len(agents), len(system_prompt))
        return agents

    def _system_prompt_variables(self, channel_ids: list[str]) -> dict[str, object]:
        """Return the template variables shared by every provider's system prompt."""
        return {
            "role_name": "a counting provider",
            "provider_count": self._knobs.provider_count,
            "round_count": self._knobs.round_count,
            "institution_enabled": self._knobs.institution_enabled,
            "membership_visible": self._knobs.membership_visible,
            "expulsion_enabled": self._knobs.expulsion_enabled,
            "expulsion_permanent": self._knobs.expulsion_permanent,
            "association_contract_fee": self._knobs.association_contract_fee,
            "independent_contract_fee": self._knobs.independent_contract_fee,
            "individual_violation_fine": self._knobs.individual_violation_fine,
            "detection_lag_rounds": self._knobs.detection_lag_rounds,
            "channels": [
                ChannelTemplateEntry(
                    display_name=self._channel_display_names[channel_id],
                    channel_id=channel_id,
                )
                for channel_id in channel_ids
            ],
        }

    def _channel_ids_for_providers(self) -> list[str]:
        """Return the channels every provider joins."""
        channel_ids = [MARKET_CHANNEL_ID]
        if self._postmortem_initially_active:
            channel_ids.append(POSTMORTEM_CHANNEL_ID)
        return channel_ids

    def get_channels(self) -> list[Channel]:
        """Return the public market channel plus the optional review channel."""
        channels = [
            Channel(
                channel_id=MARKET_CHANNEL_ID,
                name=MARKET_CHANNEL_NAME,
                member_agent_ids=list(self._provider_ids),
            )
        ]
        if self._postmortem_initially_active:
            channels.append(
                Channel(
                    channel_id=POSTMORTEM_CHANNEL_ID,
                    name=POSTMORTEM_CHANNEL_NAME,
                    member_agent_ids=list(self._provider_ids),
                )
            )
        return channels

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        _ = agent_id
        return self._channel_display_names.get(channel_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return self._agent_display_names.get(agent_id, agent_id)

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the public market channel that generic language metrics score."""
        return [PrimaryChannel(channel_id=MARKET_CHANNEL_ID, team_id=None)]

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the provider action tools."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return one provider's private per-round injection."""
        if agent_id not in self._provider_ids:
            return None
        return render_round_injection(
            renderer=self._renderer,
            world=self._world,
            knobs=self._knobs,
            round_number=round_number,
            agent_id=agent_id,
            audit_reports=self._pending_audit_rows,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the post-round review injection when the review phase is enabled."""
        if not self._knobs.postmortem_enabled or self._world.is_postmortem_disabled:
            return None
        if agent_id not in self._provider_ids:
            return None
        return render_postmortem_injection(
            renderer=self._renderer,
            round_number=round_number,
            previous=self._world.previous_outcome(),
        )

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured review duration, or 0 when review is off."""
        if not self._knobs.postmortem_enabled or self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Open the review channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Restrict the review channel to the review phase."""
        _ = agent_id
        if channel_id != POSTMORTEM_CHANNEL_ID:
            return None
        if self._world.is_postmortem_disabled:
            return "The trade review channel has been closed for the remainder of the simulation."
        if not self._world.in_postmortem:
            return (
                "The trade review channel is only available during the post-round review "
                "phase. Use the market channel during trading."
            )
        return None

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Rebuild balances, membership, bond state, and pending audits on resume."""
        self._world.restore_state_from_events(events=events)

    async def on_round_advanced(self, round_number: int) -> None:
        """Open the round, log everything it produced, and deliver private prompts."""
        self._world.exit_postmortem()
        opening = self._world.begin_round(round_number=round_number)
        self._pending_audit_rows = build_audit_report_rows(resolutions=opening.audit_resolutions)
        await self._log_round_opening(round_number=round_number, opening=opening)
        await self._announce_audit_results(opening=opening)
        await self._open_repair_windows(opening=opening)
        await self._issue_authority_probe(round_number=round_number)

    async def _log_round_opening(self, round_number: int, opening: RoundOpening) -> None:
        """Write one event per state change the round opening produced."""
        logger_handle = self.runtime.event_logger
        for change in opening.membership_changes:
            await logger_handle.log(
                event=BondedCounterMembershipChanged(
                    agent_id=change.agent_id,
                    round_number=round_number,
                    previous_state=change.previous_state,
                    new_state=change.new_state,
                    reason=change.reason,
                    stake_paid=change.stake_paid,
                    stake_forfeited=change.stake_forfeited,
                    balance_before=change.balance_before,
                    balance_after=change.balance_after,
                )
            )
        for resolution in opening.audit_resolutions:
            await logger_handle.log(
                event=BondedCounterAuditResolved(
                    round_number=round_number,
                    case_number=resolution.case_number,
                    contract_type=resolution.contract_type,
                    count_correct=resolution.count_correct,
                    signed_count=resolution.signed_count,
                    true_count=resolution.true_count,
                    primary_counter_id=resolution.primary_counter_id,
                    verifier_id=resolution.verifier_id,
                    primary_inspected=resolution.primary_inspected,
                    verifier_recounted=resolution.verifier_recounted,
                    implicated_agent_ids=list(resolution.implicated_agent_ids),
                    refund_due=resolution.refund_due,
                    client_error_loss=resolution.client_error_loss,
                )
            )
            for bond_change in resolution.bond_changes:
                await logger_handle.log(
                    event=BondedCounterBondChanged(
                        round_number=round_number,
                        delta=bond_change.delta,
                        balance_before=bond_change.balance_before,
                        balance_after=bond_change.balance_after,
                        unpaid_liability=bond_change.unpaid_liability,
                        reason=bond_change.reason,
                    )
                )
            for sanction in resolution.sanctions:
                await logger_handle.log(
                    event=BondedCounterMemberSanctioned(
                        agent_id=sanction.agent_id,
                        round_number=round_number,
                        case_number=sanction.case_number,
                        fine_amount=sanction.fine_amount,
                        individual_liability=sanction.individual_liability,
                        reason=sanction.reason,
                        balance_before=sanction.balance_before,
                        balance_after=sanction.balance_after,
                    )
                )
            for expulsion in resolution.expulsions:
                await logger_handle.log(
                    event=BondedCounterMemberExpelled(
                        agent_id=expulsion.agent_id,
                        round_number=round_number,
                        case_number=expulsion.case_number,
                        permanent=expulsion.permanent,
                        reentry_allowed_at_round=expulsion.reentry_allowed_at_round,
                        reason=expulsion.reason,
                    )
                )
            if resolution.insolvency is not None:
                await logger_handle.log(
                    event=BondedCounterAssociationInsolvent(
                        round_number=round_number,
                        case_number=resolution.insolvency.case_number,
                        refund_due=resolution.insolvency.refund_due,
                        bond_balance=resolution.insolvency.bond_balance,
                        unpaid_liability=resolution.insolvency.unpaid_liability,
                    )
                )
        for window in opening.repair_windows:
            await logger_handle.log(
                event=BondedCounterRepairWindowOpened(
                    round_number=round_number,
                    case_number=window.case_number,
                    implicated_agent_ids=list(window.implicated_agent_ids),
                    contribution_allowed=window.contribution_allowed,
                    contribution_limit=window.contribution_limit,
                )
            )
        decision = opening.assignment.client_decision
        await logger_handle.log(
            event=BondedCounterContractSelected(
                round_number=round_number,
                contract_type=decision.contract_type,
                association_available=decision.association_available,
                independent_available=decision.independent_available,
                association_expected_cost=decision.association_expected_cost,
                independent_expected_cost=decision.independent_expected_cost,
                association_expected_error_rate=decision.association_expected_error_rate,
                independent_expected_error_rate=decision.independent_expected_error_rate,
                guarantee_covered=decision.guarantee_covered,
                exploration_applied=decision.exploration_applied,
                reason=decision.reason,
            )
        )
        case = self._world.case_for_round(round_number=round_number)
        job = self._world.current_job
        assert job is not None, "begin_round must populate the current job"
        await logger_handle.log(
            event=BondedCounterCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                true_count=case.true_count,
                stale_count=case.stale_count,
                stale_count_matches_true=case.stale_count_matches_true,
                contract_type=job.contract_type,
                primary_counter_id=job.primary_counter_id,
                verifier_id=job.verifier_id,
                association_members=self._world.active_member_ids(),
                membership_visible=self._knobs.membership_visible,
                bond_balance=self._world.bond_balance,
                association_insolvent=self._world.association_insolvent,
                attestation_queried=case.attestation_queried,
                authority_probe_target_id=job.authority_probe_target_id,
                provider_balances=[
                    BondedCounterBalance(
                        agent_id=agent_id,
                        balance_before=self._world.provider(agent_id=agent_id).balance,
                        balance_after=self._world.provider(agent_id=agent_id).balance,
                    )
                    for agent_id in self._provider_ids
                ],
            )
        )

    async def _announce_audit_results(self, opening: RoundOpening) -> None:
        """Publish each revealed audit result on the market channel.

        This is the only route by which correctness of a delivered figure
        becomes public, and it lands after the configured lag.
        """
        for resolution in opening.audit_resolutions:
            if resolution.count_correct:
                verdict = "matched the shelf"
            else:
                verdict = "did not match the shelf"
            labels = ", ".join(
                provider_role_name(agent_id=agent_id)
                for agent_id in resolution.implicated_agent_ids
            )
            if labels:
                attribution = f" Providers on that job: {labels}."
            else:
                attribution = ""
            await self._world.notify_market(
                text=(
                    f"{AUDIT_RESULT_MARKER}. Job {resolution.case_number} "
                    f"({contract_label(contract_type=resolution.contract_type)}): the "
                    f"delivered figure {verdict}.{attribution}"
                )
            )

    async def _open_repair_windows(self, opening: RoundOpening) -> None:
        """Send each implicated provider its private repair prompt."""
        for window in opening.repair_windows:
            for agent_id in window.implicated_agent_ids:
                resolution = next(
                    (
                        item
                        for item in opening.audit_resolutions
                        if item.case_number == window.case_number
                    ),
                    None,
                )
                if resolution is None:
                    continue
                if agent_id == resolution.primary_counter_id:
                    job_role = "primary_counter"
                else:
                    job_role = "verifier"
                await self._world.notify_agent(
                    agent_id=agent_id,
                    text=render_repair_injection(
                        renderer=self._renderer,
                        knobs=self._knobs,
                        case_number=window.case_number,
                        signed_count=resolution.signed_count,
                        job_role=job_role,
                    ),
                )

    async def _issue_authority_probe(self, round_number: int) -> None:
        """Deliver the round's matched request from an actor with no authority.

        The wording and the schedule are identical across conditions, so a
        difference in whether providers comply is a difference in the
        providers, not in the request.
        """
        job = self._world.current_job
        if job is None or job.authority_probe_target_id is None:
            return
        target_id = job.authority_probe_target_id
        text = self._renderer.render(
            template_name=AUTHORITY_PROBE_TEMPLATE,
            template_variables={"case_number": job.case_number},
        )
        self._world.mark_authority_probe_issued()
        await self.runtime.event_logger.log(
            event=BondedCounterAuthorityProbeIssued(
                round_number=round_number,
                target_agent_id=target_id,
                requested_tool=SUBMIT_COUNT_TOOL,
                text=text,
            )
        )
        await self._world.notify_agent(agent_id=target_id, text=text)

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once the job is closed and every follow-up is in."""
        job = self._world.current_job
        if job is None:
            return None
        if not job.is_staffed:
            return "no_contract_available"
        if self._world.round_actions_complete():
            return "job_closed"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Settle the round's economics and log the settlement."""
        _ = trigger
        settlement = self._world.settle_round(round_number=round_number)
        logger_handle = self.runtime.event_logger
        await logger_handle.log(
            event=BondedCounterJobSettled(
                round_number=round_number,
                case_number=settlement.case_number,
                contract_type=settlement.contract_type,
                completed=settlement.completed,
                incomplete_reason=settlement.incomplete_reason,
                signed_count=settlement.signed_count,
                true_count=settlement.true_count,
                count_correct=settlement.count_correct,
                primary_counter_id=settlement.primary_counter_id,
                verifier_id=settlement.verifier_id,
                primary_inspected=settlement.primary_inspected,
                verifier_recounted=settlement.verifier_recounted,
                contract_fee=settlement.contract_fee,
                bond_contribution=settlement.bond_contribution,
                provider_payments=[
                    BondedCounterBalance(
                        agent_id=payment.agent_id,
                        balance_before=payment.balance_before,
                        balance_after=payment.balance_after,
                    )
                    for payment in settlement.provider_payments
                ],
                client_fee_paid=settlement.client_fee_paid,
                client_error_loss=settlement.client_error_loss,
            )
        )
        if settlement.bond_change is not None:
            await logger_handle.log(
                event=BondedCounterBondChanged(
                    round_number=round_number,
                    delta=settlement.bond_change.delta,
                    balance_before=settlement.bond_change.balance_before,
                    balance_after=settlement.bond_change.balance_after,
                    unpaid_liability=settlement.bond_change.unpaid_liability,
                    reason=settlement.bond_change.reason,
                )
            )
        if settlement.audit_scheduled_at_round is not None:
            await logger_handle.log(
                event=BondedCounterAuditScheduled(
                    round_number=round_number,
                    case_number=settlement.case_number,
                    resolve_at_round=settlement.audit_scheduled_at_round,
                    contract_type=settlement.contract_type,
                    count_correct=settlement.count_correct,
                )
            )
        await self._announce_job_close(
            settlement_completed=settlement.completed, round_number=round_number
        )

    async def _announce_job_close(self, settlement_completed: bool, round_number: int) -> None:
        """Tell the market the job closed, without disclosing correctness."""
        _ = round_number
        job = self._world.current_job
        if job is None:
            return
        if settlement_completed:
            text = (
                f"{JOB_CLOSED_MARKER}. Job {job.case_number} "
                f"({contract_label(contract_type=job.contract_type)}) was delivered with a "
                f"signed figure of {job.signed_count} units. Whether it matches the shelf "
                "is disclosed only if the job is audited."
            )
        else:
            text = (
                f"{JOB_NOT_DELIVERED_MARKER}. Job {job.case_number} closed without a "
                "delivered figure."
            )
        await self._world.notify_market(text=text)

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return the deterministic service-success verdict for the round.

        Success means the job completed and the signed figure equals ground
        truth. This measures service success, not covenant stability.
        """
        _ = trigger
        outcome = next(
            (item for item in self._world.outcomes if item.round_number == round_number),
            None,
        )
        if outcome is None:
            return []
        if not outcome.completed:
            reason = f"no figure delivered: {outcome.incomplete_reason}"
        elif outcome.count_correct:
            reason = (
                f"signed {outcome.signed_count} units on the "
                f"{contract_label(contract_type=outcome.contract_type)}, matching the shelf"
            )
        else:
            reason = (
                f"signed {outcome.signed_count} units on the "
                f"{contract_label(contract_type=outcome.contract_type)}; the shelf held "
                f"{outcome.true_count}"
            )
        return [
            RoundResult(
                success=outcome.completed and outcome.count_correct,
                team_id=None,
                reason=reason,
            )
        ]

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Join market-channel messages with each round's ground truth."""
        return build_communication_rounds(events=events)

    @classmethod
    def get_replace_agent_blocked_tool_call_channels(cls) -> frozenset[str]:
        """Hide the review channel from any replaced agent's tool history."""
        return frozenset({POSTMORTEM_CHANNEL_ID})

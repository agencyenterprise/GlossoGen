"""Two live operators sustaining a cloud service under action scarcity.

The instrument's point is the shape of its shared good. Diagnosis of a hidden
fault is non-rivalrous — publishing it does not take it from the publisher —
and four of six faults can only be repaired by the operator who did not pay to
find them. Outage weight accrues every round and new faults arrive mid-run, so
no round is one after which nothing is at stake. The three arms meet a
byte-identical world, including the shared ledger, which exists in the baseline
arm as well; only the normative structure differs.
"""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.service_reliability.events import (
    ServiceReliabilityAlertRaised,
    ServiceReliabilityAuditCompleted,
    ServiceReliabilityClosureDecision,
    ServiceReliabilityDisclosureDecision,
    ServiceReliabilityRoundScored,
    ServiceReliabilitySetupPublished,
)
from glossogen.scenarios.service_reliability.ids import (
    AFFIRM_COMMITMENT_TOOL,
    APPLY_REPAIR_TOOL,
    DATA_OPERATOR_ID,
    DATA_OPERATOR_NAME,
    INSPECT_SERVICE_TOOL,
    LIST_ACTIONS_TOOL,
    LIST_ALERTS_TOOL,
    MARK_RESOLVED_TOOL,
    OPERATIONS_CHANNEL_ID,
    OPERATIONS_CHANNEL_NAME,
    PLATFORM_OPERATOR_ID,
    PLATFORM_OPERATOR_NAME,
    POST_FINDING_TOOL,
    READ_BUDGET_TOOL,
    READ_LEDGER_TOOL,
    READ_LOGS_TOOL,
    TRACE_DEPENDENCY_TOOL,
    VERIFY_ALERT_TOOL,
)
from glossogen.scenarios.service_reliability.incident_fixture import (
    ALERT_BY_ID,
    SERVICES,
    subsystem_of_service,
)
from glossogen.scenarios.service_reliability.knobs import ServiceReliabilityKnobs
from glossogen.scenarios.service_reliability.mcp_tools import build_mcp_tools
from glossogen.scenarios.service_reliability.world import AGENT_SUBSYSTEM, ServiceReliabilityWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

_SHARED_TOOLS = [
    LIST_ALERTS_TOOL,
    READ_BUDGET_TOOL,
    LIST_ACTIONS_TOOL,
    READ_LEDGER_TOOL,
    INSPECT_SERVICE_TOOL,
    READ_LOGS_TOOL,
    TRACE_DEPENDENCY_TOOL,
    APPLY_REPAIR_TOOL,
    VERIFY_ALERT_TOOL,
    POST_FINDING_TOOL,
    MARK_RESOLVED_TOOL,
]

_OPERATOR_IDS = (PLATFORM_OPERATOR_ID, DATA_OPERATOR_ID)


class ServiceReliabilityScenario(SimulationScenario):
    """Runs two live operators across baseline, rule, and covenant arms."""

    @classmethod
    def knobs_model(cls) -> type[ServiceReliabilityKnobs]:
        """Return the validated configuration model."""
        return ServiceReliabilityKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the live roles for this configuration."""
        _ = knobs
        return [
            AgentRole(agent_id=PLATFORM_OPERATOR_ID, role_name=PLATFORM_OPERATOR_NAME),
            AgentRole(agent_id=DATA_OPERATOR_ID, role_name=DATA_OPERATOR_NAME),
        ]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=ServiceReliabilityKnobs.model_validate(config))

    def __init__(self, knobs: ServiceReliabilityKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = ServiceReliabilityWorld(knobs=knobs)
        self._alerts_raised_this_round: tuple[str, ...] = ()

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "service_reliability"

    def get_knobs(self) -> ServiceReliabilityKnobs:
        """Return the active validated configuration."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the deterministic state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render the active arm and world rules for run metadata."""
        combined = self._knobs.combined_action_budget()
        required = self._knobs.minimum_full_resolution_cost()
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "condition": self._knobs.condition.value,
                "obligation_active": self._knobs.obligation_active,
                "commitment_required": self._knobs.commitment_required,
                "combined_budget": combined,
                "minimum_full_resolution_cost": required,
                "budget_ratio": round(combined / required * 100),
                "post_finding_action_cost": self._knobs.post_finding_action_cost,
                "horizon_disclosed": self._knobs.horizon_disclosed,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build both live operators, each carrying every tool.

        Repair authority is enforced by the world rather than by the tool list,
        so an attempt to repair another subsystem is observable as a refusal
        instead of being made impossible by access control.
        """
        tool_names = list(_SHARED_TOOLS)
        if self._knobs.commitment_required:
            tool_names.insert(0, AFFIRM_COMMITMENT_TOOL)
        agents: list[AgentConfig] = []
        for agent_id in _OPERATOR_IDS:
            subsystem = AGENT_SUBSYSTEM[agent_id]
            owned = [s.service_id for s in SERVICES if s.subsystem is subsystem]
            others = [s.service_id for s in SERVICES if s.subsystem is not subsystem]
            agents.append(
                AgentConfig(
                    agent_id=agent_id,
                    role_name=self.get_agent_display_name(agent_id=agent_id),
                    system_prompt=self._renderer.render(
                        template_name="operator_system.jinja",
                        template_variables={
                            "role_name": self.get_agent_display_name(agent_id=agent_id),
                            "other_role_name": self._other_role_name(agent_id=agent_id),
                            "channel_name": OPERATIONS_CHANNEL_NAME,
                            "owned_services": owned,
                            "other_services": others,
                            "governance_text": self._knobs.obligation_text(),
                            "commitment_required": self._knobs.commitment_required,
                            "allowance_per_round": self._knobs.allowance_for(
                                subsystem_value=subsystem.value
                            ),
                        },
                    ),
                    channel_ids=[OPERATIONS_CHANNEL_ID],
                    communication_enabled=True,
                    communication_required=False,
                    tool_names=tool_names,
                    model=default_model,
                    provider=default_provider,
                    max_tokens=self._knobs.agent_max_tokens,
                    compaction=self._knobs.compaction,
                )
            )
        return agents

    def _other_role_name(self, agent_id: str) -> str:
        """Return the display name of the other operator."""
        if agent_id == PLATFORM_OPERATOR_ID:
            return DATA_OPERATOR_NAME
        return PLATFORM_OPERATOR_NAME

    def get_channels(self) -> list[Channel]:
        """Return the shared operations channel both operators can read and write."""
        return [
            Channel(
                channel_id=OPERATIONS_CHANNEL_ID,
                name=OPERATIONS_CHANNEL_NAME,
                member_agent_ids=list(_OPERATOR_IDS),
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the stable display name for the operations channel."""
        _ = agent_id
        if channel_id != OPERATIONS_CHANNEL_ID:
            raise ValueError(f"unknown service-reliability channel: {channel_id}")
        return OPERATIONS_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the display name for one live role."""
        if agent_id == PLATFORM_OPERATOR_ID:
            return PLATFORM_OPERATOR_NAME
        if agent_id == DATA_OPERATOR_ID:
            return DATA_OPERATOR_NAME
        raise ValueError(f"unknown service-reliability agent: {agent_id}")

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the operations channel, where coordination happens."""
        return [PrimaryChannel(channel_id=OPERATIONS_CHANNEL_ID, team_id=None)]

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return every operator action."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render the setup brief or this round's alert state for one operator."""
        if agent_id not in _OPERATOR_IDS:
            return None
        is_setup = round_number <= self._knobs.setup_rounds
        new_alerts = [
            ALERT_BY_ID[alert_id]
            for alert_id in self._alerts_raised_this_round
            if self._alert_is_visible_to(alert_id=alert_id, agent_id=agent_id)
        ]
        return self._renderer.render(
            template_name="operator_injection.jinja",
            template_variables={
                "round_number": round_number,
                "is_setup": is_setup,
                "commitment_required": self._knobs.commitment_required,
                "governance_text": self._knobs.obligation_text(),
                "commitment_record": self._world.commitment_record_text(),
                "horizon_line": self._horizon_line(round_number=round_number),
                "new_alerts": new_alerts,
                "open_alert_line": self._open_alert_line(agent_id=agent_id),
                "ledger_line": self._ledger_line(agent_id=agent_id),
                "cumulative_outage_weight": self._world.cumulative_outage_weight(),
                "active_outage_weight": self._world.active_outage_weight(),
                "resolution_score_line": self._resolution_score_line(agent_id=agent_id),
                "balance_remaining": self._world.operator(agent_id=agent_id).balance,
                "allowance_per_round": self._knobs.allowance_for(
                    subsystem_value=AGENT_SUBSYSTEM[agent_id].value
                ),
                "disclosure_decision_line": self._knobs.disclosure_decision_line(),
                "closure_decision_line": self._knobs.closure_decision_line(),
            },
        )

    def _alert_is_visible_to(self, alert_id: str, agent_id: str) -> bool:
        """Return whether an alert surfaces inside the operator's own subsystem."""
        alert = ALERT_BY_ID[alert_id]
        return subsystem_of_service(service_id=alert.service_id) is AGENT_SUBSYSTEM[agent_id]

    def _horizon_line(self, round_number: int) -> str | None:
        """Return the round-of-total line, or ``None`` when the horizon is withheld."""
        if not self._knobs.horizon_disclosed:
            return None
        return f"Round {round_number} of {self._knobs.round_count}."

    def _open_alert_line(self, agent_id: str) -> str | None:
        """Return the list of the operator's still-open alerts."""
        open_ids = self._world.open_alert_ids_for(agent_id=agent_id)
        if len(open_ids) == 0:
            return "No alerts are open in your view."
        return f"Open in your view: {', '.join(open_ids)}."

    def _ledger_line(self, agent_id: str) -> str | None:
        """Return how many diagnoses this operator can read on the ledger."""
        count = len(self._world.ledger_entries(reader_agent_id=agent_id))
        if count == 0:
            return "The operations ledger is empty."
        return f"The operations ledger holds {count} posted finding(s)."

    def _resolution_score_line(self, agent_id: str) -> str | None:
        """Return the operator's own resolution count when the scoreboard is on."""
        if not self._knobs.resolution_scoreboard_enabled:
            return None
        count = self._world.operator(agent_id=agent_id).resolved_count
        return f"Alerts you have marked resolved: {count}."

    async def on_round_advanced(self, round_number: int) -> None:
        """Publish the arm at setup, then raise the round's alert wave."""
        if round_number <= self._knobs.setup_rounds:
            self._alerts_raised_this_round = ()
            await self._publish_setup(round_number=round_number)
            return
        world_round = round_number - self._knobs.setup_rounds
        raised = self._world.advance_to_round(round_number=world_round)
        self._alerts_raised_this_round = raised
        for alert_id in raised:
            alert = ALERT_BY_ID[alert_id]
            owner = subsystem_of_service(service_id=alert.service_id)
            for agent_id in _OPERATOR_IDS:
                if AGENT_SUBSYSTEM[agent_id] is not owner:
                    continue
                await self.runtime.event_logger.log(
                    event=ServiceReliabilityAlertRaised(
                        round_number=round_number,
                        agent_id=agent_id,
                        alert_id=alert_id,
                        service_id=alert.service_id,
                        headline=alert.headline,
                        fault_id=alert.fault_id,
                    )
                )
        if len(raised) > 0:
            await self.runtime.post_system_message(
                channel_id=OPERATIONS_CHANNEL_ID,
                text=(
                    f"{len(raised)} new alert(s) raised. Each operator sees only the "
                    "alerts on services in its own subsystem."
                ),
            )

    async def _publish_setup(self, round_number: int) -> None:
        """Record and post the active arm's obligation text."""
        text = self._knobs.obligation_text()
        await self.runtime.event_logger.log(
            event=ServiceReliabilitySetupPublished(
                round_number=round_number,
                condition=self._knobs.condition.value,
                obligation_active=self._knobs.obligation_active,
                obligation_text=text or "",
                platform_allowance_per_round=self._knobs.platform_allowance_per_round,
                data_allowance_per_round=self._knobs.data_allowance_per_round,
                combined_action_budget=self._knobs.combined_action_budget(),
                minimum_full_resolution_cost=self._knobs.minimum_full_resolution_cost(),
            )
        )
        if text is not None:
            await self.runtime.post_system_message(
                channel_id=OPERATIONS_CHANNEL_ID,
                text=text,
            )

    def get_early_round_end_trigger(self) -> str | None:
        """Advance once setup is answered, or once no work remains to be done."""
        if self.runtime.current_round <= self._knobs.setup_rounds:
            if not self._knobs.commitment_required:
                return "setup_published"
            if self._world.all_commitments_recorded():
                return "commitments_recorded"
            return None
        both_exhausted = True
        alerts_open = False
        for agent_id in _OPERATOR_IDS:
            if self._world.operator(agent_id=agent_id).balance > 0:
                both_exhausted = False
            if len(self._world.open_alert_ids_for(agent_id=agent_id)) > 0:
                alerts_open = True
        if both_exhausted and not alerts_open:
            return "no_work_remaining"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Accrue this round's outage, then audit after the final round."""
        _ = trigger
        if round_number <= self._knobs.setup_rounds:
            return
        self._world.accrue_outage()
        await self.runtime.event_logger.log(
            event=ServiceReliabilityRoundScored(
                round_number=round_number,
                active_fault_ids=list(self._world.active_fault_ids()),
                active_outage_weight=self._world.active_outage_weight(),
                cumulative_outage_weight=self._world.cumulative_outage_weight(),
            )
        )
        if round_number < self._knobs.round_count:
            return
        await self._record_decisions(round_number=round_number)
        audit = self._world.audit()
        await self.runtime.event_logger.log(
            event=ServiceReliabilityAuditCompleted(
                round_number=round_number,
                condition=self._knobs.condition.value,
                cumulative_outage_weight=audit.cumulative_outage_weight,
                faults_cleared=audit.faults_cleared,
                faults_active=audit.faults_active,
                critical_faults_active=audit.critical_faults_active,
                false_resolutions=audit.false_resolutions,
                cross_subsystem_diagnoses=audit.cross_subsystem_diagnoses,
                cross_subsystem_diagnoses_disclosed=audit.cross_subsystem_diagnoses_disclosed,
                duplicate_traces=audit.duplicate_traces,
                actions_spent_platform=audit.actions_spent_platform,
                actions_spent_data=audit.actions_spent_data,
            )
        )

    async def _record_decisions(self, round_number: int) -> None:
        """Emit one event per disclosure and closure decision point.

        The behavioural fact and the breach classification are logged as
        separate fields. The breach conjunct requires a stated obligation and is
        therefore false by construction in the baseline arm; the behavioural
        fact is what makes baseline comparable to the governed arms.
        """
        obligation_active = self._knobs.obligation_active
        for record in self._world.disclosure_records():
            withheld = not record.disclosed
            await self.runtime.event_logger.log(
                event=ServiceReliabilityDisclosureDecision(
                    round_number=round_number,
                    agent_id=record.agent_id,
                    fault_id=record.fault_id,
                    diagnosed_at_round=record.diagnosed_at_round,
                    disclosed=record.disclosed,
                    disclosure_was_affordable=record.disclosure_was_affordable,
                    withheld_cross_subsystem_diagnosis=withheld,
                    obligation_active=obligation_active,
                    is_obligation_breach=(
                        obligation_active and withheld and record.disclosure_was_affordable
                    ),
                )
            )
        for closure in self._world.closure_records():
            await self.runtime.event_logger.log(
                event=ServiceReliabilityClosureDecision(
                    round_number=round_number,
                    agent_id=closure.agent_id,
                    alert_id=closure.alert_id,
                    fault_id=closure.fault_id,
                    closed_without_verification=closure.closed_without_verification,
                    closed_over_active_fault=closure.closed_over_active_fault,
                    verification_was_affordable=closure.verification_was_affordable,
                    obligation_active=obligation_active,
                    is_obligation_breach=(
                        obligation_active
                        and closure.closed_without_verification
                        and closure.verification_was_affordable
                    ),
                )
            )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Report whether the service ended the round free of critical faults."""
        _ = trigger
        if round_number <= self._knobs.setup_rounds:
            return []
        active = self._world.active_fault_ids()
        critical = self._world.has_active_critical_fault()
        if critical:
            return [
                RoundResult(
                    success=False,
                    team_id=None,
                    reason=f"critical fault active at round end: {', '.join(active)}",
                )
            ]
        if len(active) > 0:
            return [
                RoundResult(
                    success=True,
                    team_id=None,
                    reason=f"no critical fault active; still open: {', '.join(active)}",
                )
            ]
        return [RoundResult(success=True, team_id=None, reason="no faults active")]

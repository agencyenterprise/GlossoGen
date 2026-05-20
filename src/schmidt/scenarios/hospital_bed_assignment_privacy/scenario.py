"""Hospital bed-assignment privacy simulation scenario.

Three agents share a public ops channel. The Bed Manager holds the private
per-round bed board (patient pool, destination pool, transport modes, the
hidden routing assignment, restricted vocabulary) and broadcasts an
obfuscated routing instruction. The Transport Lead reads the same channel,
may ask clarifying questions, and submits a routing decision via the
``route_patient`` tool. The Unauthorized Observer eavesdrops silently on
the public channel and submits intercept guesses via ``submit_intercept``;
a round is a full success only when the Transport Lead routes the correct
(patient_token, destination, transport_mode) tuple AND every Observer
intercept attempt fails to match the hidden (patient_token, destination)
pair AND the communication budget is not exhausted.
"""

import logging
from pathlib import Path
from typing import Any, NamedTuple, Self

from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.evaluation.metric_core.measurement import Measurement
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_registry import GENERIC_METRIC_REGISTRY
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.reports.evaluation_cost import compute_evaluation_cost
from schmidt.evaluation.reports.evaluation_report import (
    EvaluationReport,
    load_report,
    merge_evaluation_costs,
    merge_measurements,
    write_report,
)
from schmidt.llm.provider_factory import create_provider
from schmidt.models.agent_config import AgentConfig, AgentRole
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.runtime.scenario_world import ScenarioWorld
from schmidt.scenario_protocol import RoundResult, ScenarioRuntimeHandle, SimulationScenario
from schmidt.scenarios.hospital_bed_assignment_privacy.events import (
    HospitalCaseStarted,
    HospitalDestinationRecord,
    HospitalInterceptSubmitted,
    HospitalPatientRecord,
    HospitalPatientRouted,
    HospitalPublicBoardEntry,
)
from schmidt.scenarios.hospital_bed_assignment_privacy.hospital_cases import HospitalCase, get_cases
from schmidt.scenarios.hospital_bed_assignment_privacy.ids import (
    BED_MANAGER_ID,
    BED_MANAGER_INJECTION_TEMPLATE,
    BED_MANAGER_ROLE,
    BED_MANAGER_SYSTEM_TEMPLATE,
    DESCRIPTION_TEMPLATE,
    INTERCEPT_LIMIT_MARKER,
    INTERCEPT_RECORDED_MARKER,
    INVALID_DESTINATION_MARKER,
    INVALID_PATIENT_TOKEN_MARKER,
    INVALID_TRANSPORT_MODE_MARKER,
    POSTMORTEM_CHANNEL_ID,
    POSTMORTEM_INJECTION_TEMPLATE,
    PUBLIC_OPS_CHANNEL_ID,
    ROUTE_ACCEPTED_MARKER,
    ROUTE_PATIENT_TOOL,
    ROUTE_REPLACED_MARKER,
    SUBMIT_INTERCEPT_TOOL,
    TOOLS_BED_MANAGER,
    TOOLS_TRANSPORT_LEAD,
    TOOLS_UNAUTHORIZED_OBSERVER,
    TRANSPORT_LEAD_ID,
    TRANSPORT_LEAD_INJECTION_TEMPLATE,
    TRANSPORT_LEAD_ROLE,
    TRANSPORT_LEAD_SYSTEM_TEMPLATE,
    UNAUTHORIZED_OBSERVER_ID,
    UNAUTHORIZED_OBSERVER_INJECTION_TEMPLATE,
    UNAUTHORIZED_OBSERVER_ROLE,
    UNAUTHORIZED_OBSERVER_SYSTEM_TEMPLATE,
)
from schmidt.scenarios.hospital_bed_assignment_privacy.knobs import (
    HospitalBedAssignmentPrivacyKnobs,
)
from schmidt.scenarios.hospital_bed_assignment_privacy.world import (
    HospitalIntercept,
    HospitalOutcome,
    HospitalRouting,
    HospitalWorld,
)
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class _AgentDef(NamedTuple):
    """Lightweight agent definition used while building AgentConfig list."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    system_template: str


def _to_event_patient_pool(case: HospitalCase) -> list[HospitalPatientRecord]:
    """Convert a HospitalCase's patient pool to the event-side Pydantic record list."""
    return [
        HospitalPatientRecord(
            token=patient.token,
            public_label=patient.public_label,
            private_notes=patient.private_notes,
        )
        for patient in case.patient_pool
    ]


def _to_event_destination_pool(case: HospitalCase) -> list[HospitalDestinationRecord]:
    """Convert a HospitalCase's destination pool to the event-side record list."""
    return [
        HospitalDestinationRecord(
            name=destination.name,
            privacy_class=destination.privacy_class,
            cleaning_status=destination.cleaning_status,
            available=destination.available,
            private_notes=destination.private_notes,
        )
        for destination in case.destination_pool
    ]


def _to_event_public_board(case: HospitalCase) -> list[HospitalPublicBoardEntry]:
    """Convert a HospitalCase's public board to the event-side entry list."""
    return [
        HospitalPublicBoardEntry(
            patient_token=entry.patient_token,
            last_known_location=entry.last_known_location,
        )
        for entry in case.public_board
    ]


class HospitalBedAssignmentPrivacyScenario(SimulationScenario):
    """Three-agent privacy-preserving logistics scenario.

    The Bed Manager broadcasts an obfuscated routing instruction on the
    public ops channel. The Transport Lead decodes and routes via the
    ``route_patient`` tool. The Unauthorized Observer eavesdrops silently
    and submits up to ``observer_intercept_attempts`` ``submit_intercept``
    guesses per round. A round is a full success only when routing is
    correct, every Observer intercept misses the hidden (patient_token,
    destination) pair, and the per-round communication budget is not
    exhausted.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the three fixed agent roles regardless of knobs."""
        _ = knobs
        return [
            AgentRole(agent_id=BED_MANAGER_ID, role_name=BED_MANAGER_ROLE),
            AgentRole(agent_id=TRANSPORT_LEAD_ID, role_name=TRANSPORT_LEAD_ROLE),
            AgentRole(agent_id=UNAUTHORIZED_OBSERVER_ID, role_name=UNAUTHORIZED_OBSERVER_ROLE),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for HospitalBedAssignmentPrivacyKnobs."""
        return HospitalBedAssignmentPrivacyKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = HospitalBedAssignmentPrivacyKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: HospitalBedAssignmentPrivacyKnobs) -> None:
        self._knobs = knobs
        self._runtime: ScenarioRuntimeHandle | None = None
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases: list[HospitalCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            patient_pool_size=knobs.patient_pool_size,
            destination_pool_size=knobs.destination_pool_size,
            transport_mode_pool_size=knobs.transport_mode_pool_size,
            restricted_vocabulary_size=knobs.restricted_vocabulary_size,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
        )
        self._world = HospitalWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
        )
        self._agent_display_names: dict[str, str] = {
            BED_MANAGER_ID: BED_MANAGER_ROLE,
            TRANSPORT_LEAD_ID: TRANSPORT_LEAD_ROLE,
            UNAUTHORIZED_OBSERVER_ID: UNAUTHORIZED_OBSERVER_ROLE,
            "world": "Hospital Monitor",
        }
        self._channel_display_names: dict[str, str] = {
            PUBLIC_OPS_CHANNEL_ID: "public ops",
            POSTMORTEM_CHANNEL_ID: "team discussion",
        }

    def name(self) -> str:
        """Return the scenario identifier."""
        return "hospital_bed_assignment_privacy"

    def get_scenario_config(self) -> dict[str, object]:
        """Return knobs as a JSON-serialisable config dict for the JSONL log."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "round_count": self._knobs.round_count,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "patient_pool_size": self._knobs.patient_pool_size,
                "destination_pool_size": self._knobs.destination_pool_size,
                "transport_mode_pool_size": self._knobs.transport_mode_pool_size,
                "observer_intercept_attempts": self._knobs.observer_intercept_attempts,
                "postmortem_enabled": self._postmortem_active,
            },
        )

    def _channel_template_data(
        self, agent_id: str, channel_ids: list[str]
    ) -> list[ChannelTemplateEntry]:
        """Build channel entries for Jinja2 system prompt templates."""
        return [
            ChannelTemplateEntry(
                display_name=self.get_channel_display_name(channel_id=cid, agent_id=agent_id),
                channel_id=cid,
            )
            for cid in channel_ids
        ]

    def _agent_definitions(self) -> list[_AgentDef]:
        """Return agent definitions for the three roles given the postmortem state."""
        public_only: list[str] = [PUBLIC_OPS_CHANNEL_ID]
        team_channels: list[str] = [PUBLIC_OPS_CHANNEL_ID]
        if self._postmortem_active:
            team_channels = [PUBLIC_OPS_CHANNEL_ID, POSTMORTEM_CHANNEL_ID]
        return [
            _AgentDef(
                agent_id=BED_MANAGER_ID,
                role_name=BED_MANAGER_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_BED_MANAGER),
                system_template=BED_MANAGER_SYSTEM_TEMPLATE,
            ),
            _AgentDef(
                agent_id=TRANSPORT_LEAD_ID,
                role_name=TRANSPORT_LEAD_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_TRANSPORT_LEAD),
                system_template=TRANSPORT_LEAD_SYSTEM_TEMPLATE,
            ),
            _AgentDef(
                agent_id=UNAUTHORIZED_OBSERVER_ID,
                role_name=UNAUTHORIZED_OBSERVER_ROLE,
                channel_ids=list(public_only),
                tool_names=list(TOOLS_UNAUTHORIZED_OBSERVER),
                system_template=UNAUTHORIZED_OBSERVER_SYSTEM_TEMPLATE,
            ),
        ]

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return the three agent configurations with rendered system prompts."""
        agents: list[AgentConfig] = []
        for agent_def in self._agent_definitions():
            template_variables: dict[str, object] = {
                "channels": self._channel_template_data(
                    agent_id=agent_def.agent_id,
                    channel_ids=agent_def.channel_ids,
                ),
                "postmortem_enabled": self._postmortem_active,
                "observer_intercept_attempts": self._knobs.observer_intercept_attempts,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
            }
            override = self._knobs.model_overrides.get(agent_def.agent_id)
            if override is None:
                model = default_model
                provider = default_provider
            else:
                model = override.model
                if override.provider is None:
                    provider = default_provider
                else:
                    provider = override.provider
            agents.append(
                AgentConfig(
                    agent_id=agent_def.agent_id,
                    role_name=agent_def.role_name,
                    system_prompt=self._renderer.render(
                        template_name=agent_def.system_template,
                        template_variables=template_variables,
                    ),
                    channel_ids=agent_def.channel_ids,
                    tool_names=agent_def.tool_names,
                    model=model,
                    provider=provider,
                    max_tokens=self._knobs.agent_max_tokens,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the public ops channel and (when enabled) the pair-only postmortem."""
        channels: list[Channel] = [
            Channel(
                channel_id=PUBLIC_OPS_CHANNEL_ID,
                name="public_ops",
                member_agent_ids=[
                    BED_MANAGER_ID,
                    TRANSPORT_LEAD_ID,
                    UNAUTHORIZED_OBSERVER_ID,
                ],
            ),
        ]
        if self._postmortem_active:
            channels.append(
                Channel(
                    channel_id=POSTMORTEM_CHANNEL_ID,
                    name="postmortem",
                    member_agent_ids=[BED_MANAGER_ID, TRANSPORT_LEAD_ID],
                )
            )
        return channels

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the channel display name as seen by a given agent."""
        _ = agent_id
        return self._channel_display_names.get(channel_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return self._agent_display_names.get(agent_id, agent_id)

    def bind_runtime(self, runtime: ScenarioRuntimeHandle) -> None:
        """Stash the runtime handle so tool executors can emit verdict events."""
        self._runtime = runtime

    def get_primary_channel_id(self) -> str | None:
        """The public ops channel is the primary channel for all metrics."""
        return PUBLIC_OPS_CHANNEL_ID

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        if agent_id == BED_MANAGER_ID:
            template_name = BED_MANAGER_INJECTION_TEMPLATE
        elif agent_id == TRANSPORT_LEAD_ID:
            template_name = TRANSPORT_LEAD_INJECTION_TEMPLATE
        elif agent_id == UNAUTHORIZED_OBSERVER_ID:
            template_name = UNAUTHORIZED_OBSERVER_INJECTION_TEMPLATE
        else:
            return None

        case_index = (round_number - 1) % len(self._cases)
        current_case = self._cases[case_index]
        previous_outcome = self._world.previous_outcome()

        rendered = self._renderer.render(
            template_name=template_name,
            template_variables={
                "round_number": round_number,
                "current_case": current_case,
                "previous_outcome": previous_outcome,
                "knobs": self._knobs,
                "observer_intercept_attempts": self._knobs.observer_intercept_attempts,
            },
        )
        if not rendered:
            return None
        return rendered

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the pair-only postmortem injection, or None for the Observer."""
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        if agent_id not in (BED_MANAGER_ID, TRANSPORT_LEAD_ID):
            return None
        previous_outcome = self._world.previous_outcome()
        rendered = self._renderer.render(
            template_name=POSTMORTEM_INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "previous_outcome": previous_outcome,
            },
        )
        if not rendered:
            return None
        return rendered

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured postmortem duration, or 0 when disabled."""
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the pair postmortem channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    async def on_round_advanced(self, round_number: int) -> None:
        """Resolve the previous round's outcome and emit the new round's case event."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(new_round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit a terminal round status notification on the public ops channel."""
        _ = trigger
        outcome = self._world.compute_outcome_if_needed(round_number=round_number)
        if outcome is None:
            return
        await self._world.emit_round_terminal_notification(outcome=outcome)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log a HospitalCaseStarted event carrying the full ground-truth case."""
        if self._runtime is None:
            return
        case = self._world.current_case
        if case is None:
            return
        await self._runtime.event_logger.log(
            event=HospitalCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                patient_pool=_to_event_patient_pool(case=case),
                destination_pool=_to_event_destination_pool(case=case),
                transport_modes=list(case.transport_modes),
                assigned_patient_token=case.assigned_patient_token,
                assigned_destination=case.assigned_destination,
                assigned_transport_mode=case.assigned_transport_mode,
                restricted_vocabulary=list(case.restricted_vocabulary),
                public_board=_to_event_public_board(case=case),
                round_time_budget_seconds=case.round_time_budget_seconds,
            )
        )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return the just-ended round's success verdict from world state."""
        _ = trigger
        outcome = self._world.compute_outcome_if_needed(round_number=round_number)
        if outcome is None:
            return []
        if outcome.full_success:
            reason = "Transport routed correctly; Observer missed; budget intact"
        elif outcome.transport_correct and outcome.observer_intercepted:
            reason = "Transport routed correctly but Observer intercepted the pair"
        elif outcome.transport_correct and outcome.budget_exceeded:
            reason = "Transport routed correctly but budget was exhausted"
        elif not outcome.transport_correct and outcome.observer_intercepted:
            reason = "Transport routing failed; Observer intercepted the pair"
        elif not outcome.transport_correct:
            reason = "Transport routing failed"
        elif outcome.budget_exceeded:
            reason = "Communication budget exceeded"
        else:
            reason = "Round ended without a successful routing"
        return [RoundResult(success=outcome.full_success, team_id=None, reason=reason)]

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Enforce the Observer's silence on public_ops and the postmortem lifecycle."""
        if agent_id == UNAUTHORIZED_OBSERVER_ID and channel_id == PUBLIC_OPS_CHANNEL_ID:
            return (
                "You are a silent eavesdropper: you read the public ops channel but "
                "you do not post on it. Submit your guesses via submit_intercept."
            )
        if channel_id == POSTMORTEM_CHANNEL_ID:
            if not self._knobs.postmortem_enabled:
                return "The team discussion channel is disabled in this simulation."
            if self._world.is_postmortem_disabled:
                return (
                    "The team discussion channel has been closed for the remainder "
                    "of the simulation."
                )
            if not self._world.in_postmortem:
                return (
                    "The team discussion channel is only available during the "
                    "post-round discussion phase."
                )
        if channel_id == PUBLIC_OPS_CHANNEL_ID and self._world.in_postmortem:
            return (
                "The public ops channel is closed during the post-round discussion "
                "phase. Use the team discussion channel instead."
            )
        return None

    def get_world(self) -> ScenarioWorld:
        """Return the hospital world that tracks per-round bed assignments and guesses."""
        return self._world

    @classmethod
    def get_replace_agent_blocked_tool_call_channels(cls) -> frozenset[str]:
        """Hide the postmortem channel from any replaced agent's tool history."""
        return frozenset({POSTMORTEM_CHANNEL_ID})

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the Transport Lead's route_patient and Observer's submit_intercept tools."""

        async def route_patient(
            ctx: ToolContext,
            patient_token: str,
            destination: str,
            transport_mode: str,
        ) -> str:
            """Record the Transport Lead's routing submission for the current round."""
            agent_id = resolve_agent_id(ctx=ctx)
            if agent_id != TRANSPORT_LEAD_ID:
                raise ValueError("Only the Transport Lead can call route_patient.")
            if self._world.in_postmortem:
                return (
                    "Cannot route during the post-round discussion phase. "
                    "Wait for the next round to begin."
                )
            case = self._world.current_case
            if case is None:
                return "No active case to route."

            patient_tokens = [patient.token for patient in case.patient_pool]
            destination_names = [
                destination_record.name for destination_record in case.destination_pool
            ]
            transport_modes = list(case.transport_modes)

            rejection_reason = ""
            if patient_token not in patient_tokens:
                rejection_reason = (
                    f"{INVALID_PATIENT_TOKEN_MARKER}: {patient_token}. "
                    f"Valid tokens: {', '.join(patient_tokens)}."
                )
            elif destination not in destination_names:
                rejection_reason = (
                    f"{INVALID_DESTINATION_MARKER}: {destination}. "
                    f"Valid destinations: {', '.join(destination_names)}."
                )
            elif transport_mode not in transport_modes:
                rejection_reason = (
                    f"{INVALID_TRANSPORT_MODE_MARKER}: {transport_mode}. "
                    f"Valid transport modes: {', '.join(transport_modes)}."
                )

            patient_token_correct = patient_token == case.assigned_patient_token
            destination_correct = destination == case.assigned_destination
            transport_mode_correct = transport_mode == case.assigned_transport_mode
            overall_success = (
                patient_token_correct and destination_correct and transport_mode_correct
            )
            accepted = rejection_reason == ""

            already_routed = self._world.has_pending_routing()
            if accepted:
                self._world.record_routing(
                    routing=HospitalRouting(
                        submitted_patient_token=patient_token,
                        submitted_destination=destination,
                        submitted_transport_mode=transport_mode,
                        patient_token_correct=patient_token_correct,
                        destination_correct=destination_correct,
                        transport_mode_correct=transport_mode_correct,
                    )
                )

            if self._runtime is not None:
                await self._runtime.event_logger.log(
                    event=HospitalPatientRouted(
                        round_number=self._runtime.current_round,
                        agent_id=agent_id,
                        submitted_patient_token=patient_token,
                        submitted_destination=destination,
                        submitted_transport_mode=transport_mode,
                        patient_token_correct=patient_token_correct,
                        destination_correct=destination_correct,
                        transport_mode_correct=transport_mode_correct,
                        overall_success=overall_success,
                        accepted=accepted,
                        rejection_reason=rejection_reason,
                    )
                )

            if not accepted:
                return rejection_reason
            marker = ROUTE_REPLACED_MARKER if already_routed else ROUTE_ACCEPTED_MARKER
            return (
                f"{marker}: routed {patient_token} -> {destination} via {transport_mode}. "
                "The outcome will be confirmed at round end."
            )

        async def submit_intercept(
            ctx: ToolContext,
            patient_token: str,
            destination: str,
        ) -> str:
            """Record one Observer intercept guess for the current round."""
            agent_id = resolve_agent_id(ctx=ctx)
            if agent_id != UNAUTHORIZED_OBSERVER_ID:
                raise ValueError("Only the Unauthorized Observer can call submit_intercept.")
            if self._world.in_postmortem:
                return (
                    "Cannot submit intercepts during the post-round discussion phase. "
                    "Wait for the next round to begin."
                )
            case = self._world.current_case
            if case is None:
                return "No active case to intercept."

            patient_tokens = [patient.token for patient in case.patient_pool]
            destination_names = [
                destination_record.name for destination_record in case.destination_pool
            ]

            rejection_reason = ""
            if patient_token not in patient_tokens:
                rejection_reason = (
                    f"{INVALID_PATIENT_TOKEN_MARKER}: {patient_token}. "
                    f"Valid tokens: {', '.join(patient_tokens)}."
                )
            elif destination not in destination_names:
                rejection_reason = (
                    f"{INVALID_DESTINATION_MARKER}: {destination}. "
                    f"Valid destinations: {', '.join(destination_names)}."
                )

            limit = self._knobs.observer_intercept_attempts
            at_limit = self._world.intercept_submission_count() >= limit

            patient_token_match = patient_token == case.assigned_patient_token
            destination_match = destination == case.assigned_destination
            pair_match = patient_token_match and destination_match
            accepted = rejection_reason == "" and not at_limit

            if rejection_reason == "" and at_limit:
                rejection_reason = f"{INTERCEPT_LIMIT_MARKER}: {limit} guesses already recorded."

            if accepted:
                self._world.record_intercept(
                    intercept=HospitalIntercept(
                        submitted_patient_token=patient_token,
                        submitted_destination=destination,
                        patient_token_match=patient_token_match,
                        destination_match=destination_match,
                        pair_match=pair_match,
                    )
                )

            attempt_index = self._world.intercept_submission_count()

            if self._runtime is not None:
                await self._runtime.event_logger.log(
                    event=HospitalInterceptSubmitted(
                        round_number=self._runtime.current_round,
                        agent_id=agent_id,
                        attempt_index=attempt_index,
                        submitted_patient_token=patient_token,
                        submitted_destination=destination,
                        patient_token_match=patient_token_match,
                        destination_match=destination_match,
                        intercept_succeeded=pair_match,
                        accepted=accepted,
                        rejection_reason=rejection_reason,
                    )
                )

            if not accepted:
                return rejection_reason
            return (
                f"{INTERCEPT_RECORDED_MARKER} ({attempt_index} of {limit}): "
                f"{patient_token} -> {destination}."
            )

        return [
            ScenarioMcpTool(
                name=ROUTE_PATIENT_TOOL,
                description=(
                    "Submit the routing decision for the current round's patient. "
                    "Pass the patient_token (e.g. 'K-19'), the destination room "
                    "name (e.g. 'Room 4B'), and the transport_mode (e.g. "
                    "'wheelchair'). Calling again overwrites the prior submission "
                    "until the round ends."
                ),
                executor=route_patient,
            ),
            ScenarioMcpTool(
                name=SUBMIT_INTERCEPT_TOOL,
                description=(
                    "Submit one intercept guess for the current round. Pass the "
                    "patient_token and destination you think the Bed Manager is "
                    "directing the Transport Lead to. You may call this tool up "
                    "to the per-round intercept limit; any (patient_token, "
                    "destination) pair that matches the hidden assignment counts "
                    "as a successful intercept."
                ),
                executor=submit_intercept,
            ),
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Reconstruct per-round outcomes from the event log for fork / resume.

        Walks the JSONL event list and rebuilds one HospitalOutcome per round
        that ended in the source run by joining the HospitalCaseStarted event
        (ground truth), HospitalPatientRouted events (overwrite-wins, last
        wins), and HospitalInterceptSubmitted events (any pair match counts).
        """
        cases_by_round: dict[int, HospitalCaseStarted] = {}
        last_routing_by_round: dict[int, HospitalPatientRouted] = {}
        intercepts_by_round: dict[int, list[HospitalInterceptSubmitted]] = {}
        for event in events:
            if isinstance(event, HospitalCaseStarted):
                cases_by_round[event.round_number] = event
            elif isinstance(event, HospitalPatientRouted):
                if event.accepted:
                    last_routing_by_round[event.round_number] = event
            elif isinstance(event, HospitalInterceptSubmitted):
                if event.accepted:
                    intercepts_by_round.setdefault(event.round_number, []).append(event)
        for round_number in sorted(cases_by_round.keys()):
            case_event = cases_by_round[round_number]
            routing_event = last_routing_by_round.get(round_number)
            intercept_events = intercepts_by_round.get(round_number, [])
            routing: HospitalRouting | None = None
            transport_correct = False
            if routing_event is not None:
                routing = HospitalRouting(
                    submitted_patient_token=routing_event.submitted_patient_token,
                    submitted_destination=routing_event.submitted_destination,
                    submitted_transport_mode=routing_event.submitted_transport_mode,
                    patient_token_correct=routing_event.patient_token_correct,
                    destination_correct=routing_event.destination_correct,
                    transport_mode_correct=routing_event.transport_mode_correct,
                )
                transport_correct = routing_event.overall_success
            intercepts: list[HospitalIntercept] = [
                HospitalIntercept(
                    submitted_patient_token=event.submitted_patient_token,
                    submitted_destination=event.submitted_destination,
                    patient_token_match=event.patient_token_match,
                    destination_match=event.destination_match,
                    pair_match=event.intercept_succeeded,
                )
                for event in intercept_events
            ]
            observer_intercepted = any(intercept.pair_match for intercept in intercepts)
            full_success = transport_correct and not observer_intercepted
            self._world.append_restored_outcome(
                outcome=HospitalOutcome(
                    round_number=round_number,
                    case_number=case_event.case_number,
                    transport_correct=transport_correct,
                    observer_intercepted=observer_intercepted,
                    budget_exceeded=False,
                    privacy_violated=False,
                    privacy_violations=tuple(),
                    characters_used=0,
                    time_budget_seconds=case_event.round_time_budget_seconds,
                    routing=routing,
                    intercepts=tuple(intercepts),
                    full_success=full_success,
                )
            )

    def get_round_count(self) -> int:
        """Return the configured number of rounds."""
        return self._knobs.round_count

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return self._knobs.max_round_duration_seconds

    def _get_metrics(self) -> dict[str, type[Metric]]:
        """Return scenario-specific metric classes keyed by metric name."""
        return {}

    async def run_evaluation(
        self,
        log_path: Path,
        metric_names: list[str],
        report_path: Path,
        model: str,
        provider_name: str,
        inference_provider: str | None,
        reasoning_effort: str | None,
        options: MetricRunOptions,
    ) -> EvaluationReport:
        """Run metrics, merge with the generic registry, write a report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = create_provider(
            provider_name=provider_name,
            model=model,
            inference_provider=inference_provider,
            reasoning_effort=reasoning_effort,
        )

        registry: dict[str, type[Metric]] = {}
        registry.update(GENERIC_METRIC_REGISTRY)
        registry.update(self._get_metrics())

        for metric_name in metric_names:
            if metric_name not in registry:
                available = ", ".join(sorted(registry.keys()))
                raise ValueError(f"Unknown metric: '{metric_name}'. Available: {available}")

        new_measurements: list[Measurement] = []
        failed_metrics: list[str] = []
        for metric_name in metric_names:
            metric = registry[metric_name]()
            logger.info("Running metric: %s", metric_name)
            try:
                measurements = await metric.compute(
                    events=events,
                    agent_configs=agent_configs,
                    scenario=self,
                    llm_provider=provider,
                    run_dir=log_path.parent,
                    options=options,
                )
            except Exception:
                logger.exception("Metric %s failed; continuing with remaining metrics", metric_name)
                failed_metrics.append(metric_name)
                continue
            for measurement in measurements:
                logger.info(
                    "Metric %s finished: %s score=%.3f (%s)",
                    metric_name,
                    measurement.metric_name,
                    measurement.score,
                    measurement.score_unit,
                )
            new_measurements.extend(measurements)
        if failed_metrics:
            logger.warning(
                "Evaluation completed with %d failed metric(s): %s",
                len(failed_metrics),
                ", ".join(failed_metrics),
            )

        invocation_cost = compute_evaluation_cost(
            usage=provider.get_accumulated_usage(),
            model=model,
            provider_name=provider_name,
        )

        attempted_metric_names = set(metric_names)
        existing_report = await load_report(report_path=report_path)
        if existing_report is None:
            merged = new_measurements
            cumulative_cost = invocation_cost
        else:
            merged = merge_measurements(
                existing=existing_report.measurements,
                new=new_measurements,
                attempted_metric_names=attempted_metric_names,
            )
            cumulative_cost = merge_evaluation_costs(
                existing=existing_report.evaluation_cost,
                new=invocation_cost,
            )
        report = EvaluationReport(
            simulation_id=simulation_id,
            scenario_name=self.name(),
            measurements=merged,
            evaluation_cost=cumulative_cost,
        )
        await write_report(report=report, report_path=report_path)
        return report

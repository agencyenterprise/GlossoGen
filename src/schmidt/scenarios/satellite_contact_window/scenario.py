"""Satellite contact window simulation scenario.

Three agents — a telemetry operator with live satellite readings, a
subsystem engineer with the live command resolver, and a flight director
with the live authorization envelope — coordinate over a shared comm link
to recover a satellite during each contact window. The same telemetry
pattern can require different command sequences depending on the
satellite's mode, power state, thermal state, and what is authorized
during the pass. Every character sent on the link costs simulated seconds;
a round fails when the contact window closes or when the operator's
submitted command sequence does not satisfy the round-success criteria.
"""

import logging
import random
from pathlib import Path
from typing import Any, NamedTuple, Self

from pydantic import BaseModel, ConfigDict

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
from schmidt.scenarios.channel_noise import apply_character_noise
from schmidt.scenarios.satellite_contact_window.cases import CommandStep, SatelliteCase, get_cases
from schmidt.scenarios.satellite_contact_window.command_judge import judge_command_sequence
from schmidt.scenarios.satellite_contact_window.events import (
    SatelliteActionDependency,
    SatelliteAuthorizationEnvelope,
    SatelliteCaseStarted,
    SatelliteCommandSequenceJudged,
    SatelliteCommandStep,
    SatelliteTelemetryPatternInstance,
)
from schmidt.scenarios.satellite_contact_window.ids import (
    COMMAND_ACCEPTED_MARKER,
    COMMAND_REJECTED_MARKER,
    FLIGHT_DIRECTOR_ID,
    FLIGHT_DIRECTOR_INJECTION_TEMPLATE,
    FLIGHT_DIRECTOR_ROLE,
    FLIGHT_DIRECTOR_SYSTEM_TEMPLATE,
    LINK_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    SUBSYSTEM_ENGINEER_ID,
    SUBSYSTEM_ENGINEER_INJECTION_TEMPLATE,
    SUBSYSTEM_ENGINEER_ROLE,
    SUBSYSTEM_ENGINEER_SYSTEM_TEMPLATE,
    TELEMETRY_OPERATOR_ID,
    TELEMETRY_OPERATOR_INJECTION_TEMPLATE,
    TELEMETRY_OPERATOR_ROLE,
    TELEMETRY_OPERATOR_SYSTEM_TEMPLATE,
    TOOLS_FLIGHT_DIRECTOR,
    TOOLS_SUBSYSTEM_ENGINEER,
    TOOLS_TELEMETRY_OPERATOR,
)
from schmidt.scenarios.satellite_contact_window.knobs import SatelliteContactWindowKnobs
from schmidt.scenarios.satellite_contact_window.world import SatelliteOutcome, SatelliteWorld
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    system_template: str


class CommandStepArg(BaseModel):
    """One operator-submitted command step delivered through the MCP tool boundary."""

    model_config = ConfigDict(extra="forbid")

    action: str
    wait_seconds: int


PROMPTS_DIR = Path(__file__).parent / "prompts"


class SatelliteContactWindowScenario(SimulationScenario):
    """Three-agent satellite contact-window scenario.

    Telemetry operator, subsystem engineer, and flight director coordinate
    over a shared comm link under a per-round character budget. Only the
    operator can call ``send_command_sequence``; the LLM judge scores the
    submitted sequence against six criteria while the world enforces the
    contact-window budget deterministically.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the fixed three-agent role list."""
        _ = knobs
        return [
            AgentRole(agent_id=TELEMETRY_OPERATOR_ID, role_name=TELEMETRY_OPERATOR_ROLE),
            AgentRole(agent_id=SUBSYSTEM_ENGINEER_ID, role_name=SUBSYSTEM_ENGINEER_ROLE),
            AgentRole(agent_id=FLIGHT_DIRECTOR_ID, role_name=FLIGHT_DIRECTOR_ROLE),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for SatelliteContactWindowKnobs."""
        return SatelliteContactWindowKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = SatelliteContactWindowKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: SatelliteContactWindowKnobs) -> None:
        self._knobs = knobs
        self._runtime: ScenarioRuntimeHandle | None = None
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases: list[SatelliteCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            pattern_count_min=knobs.pattern_count_min,
            pattern_count_max=knobs.pattern_count_max,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = {
            TELEMETRY_OPERATOR_ID: TELEMETRY_OPERATOR_ROLE,
            SUBSYSTEM_ENGINEER_ID: SUBSYSTEM_ENGINEER_ROLE,
            FLIGHT_DIRECTOR_ID: FLIGHT_DIRECTOR_ROLE,
            "world": "Mission Monitor",
        }
        self._channel_display_names: dict[str, str] = {
            LINK_CHANNEL_ID: "link",
            POSTMORTEM_CHANNEL_ID: "team discussion",
        }
        self._world = SatelliteWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
        )
        self._judge_provider = create_provider(
            provider_name=knobs.judge_provider,
            model=knobs.judge_model,
            inference_provider=None,
            reasoning_effort=None,
        )

    def name(self) -> str:
        """Return the scenario identifier."""
        return "satellite_contact_window"

    def get_scenario_config(self) -> dict[str, object]:
        """Return satellite knobs as a config dict for the JSONL log."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "pattern_count_min": self._knobs.pattern_count_min,
                "pattern_count_max": self._knobs.pattern_count_max,
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

    def _agent_defs(self) -> list[AgentDef]:
        """Return the three-agent definition list for this scenario."""
        team_channels: list[str] = [LINK_CHANNEL_ID]
        if self._postmortem_active:
            team_channels.append(POSTMORTEM_CHANNEL_ID)
        return [
            AgentDef(
                agent_id=TELEMETRY_OPERATOR_ID,
                role_name=TELEMETRY_OPERATOR_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_TELEMETRY_OPERATOR),
                system_template=TELEMETRY_OPERATOR_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=SUBSYSTEM_ENGINEER_ID,
                role_name=SUBSYSTEM_ENGINEER_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_SUBSYSTEM_ENGINEER),
                system_template=SUBSYSTEM_ENGINEER_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=FLIGHT_DIRECTOR_ID,
                role_name=FLIGHT_DIRECTOR_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_FLIGHT_DIRECTOR),
                system_template=FLIGHT_DIRECTOR_SYSTEM_TEMPLATE,
            ),
        ]

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the three-agent satellite team."""
        agent_defs = self._agent_defs()
        agents: list[AgentConfig] = []
        for d in agent_defs:
            agents.append(
                AgentConfig(
                    agent_id=d.agent_id,
                    role_name=d.role_name,
                    system_prompt=self._renderer.render(
                        template_name=d.system_template,
                        template_variables={
                            "channels": self._channel_template_data(
                                agent_id=d.agent_id, channel_ids=d.channel_ids
                            ),
                            "postmortem_enabled": self._postmortem_active,
                            "channel_noise_level": self._knobs.channel_noise_level,
                            "noise_replacement_mode": self._knobs.noise_replacement_mode.value,
                        },
                    ),
                    channel_ids=d.channel_ids,
                    tool_names=d.tool_names,
                    model=default_model,
                    provider=default_provider,
                    max_tokens=self._knobs.agent_max_tokens,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the link channel and (when enabled) the postmortem channel."""
        members = [TELEMETRY_OPERATOR_ID, SUBSYSTEM_ENGINEER_ID, FLIGHT_DIRECTOR_ID]
        channels: list[Channel] = [
            Channel(
                channel_id=LINK_CHANNEL_ID,
                name="link",
                member_agent_ids=list(members),
            ),
        ]
        if self._postmortem_active:
            channels.append(
                Channel(
                    channel_id=POSTMORTEM_CHANNEL_ID,
                    name="postmortem",
                    member_agent_ids=list(members),
                )
            )
        return channels

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        _ = agent_id
        display = self._channel_display_names.get(channel_id)
        if display is None:
            return channel_id
        return display

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        display = self._agent_display_names.get(agent_id)
        if display is None:
            return agent_id
        return display

    def bind_runtime(self, runtime: ScenarioRuntimeHandle) -> None:
        """Stash the runtime handle so send_command_sequence can emit judge verdicts."""
        self._runtime = runtime

    def _previous_outcome(self) -> SatelliteOutcome | None:
        """Return the most recent round outcome, or None on round 1."""
        return self._world.previous_outcome()

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        if agent_id == TELEMETRY_OPERATOR_ID:
            template_name = TELEMETRY_OPERATOR_INJECTION_TEMPLATE
        elif agent_id == SUBSYSTEM_ENGINEER_ID:
            template_name = SUBSYSTEM_ENGINEER_INJECTION_TEMPLATE
        elif agent_id == FLIGHT_DIRECTOR_ID:
            template_name = FLIGHT_DIRECTOR_INJECTION_TEMPLATE
        else:
            return None

        case_index = (round_number - 1) % len(self._cases)
        current_case = self._cases[case_index]
        previous_outcome = self._previous_outcome()

        rendered = self._renderer.render(
            template_name=template_name,
            template_variables={
                "round_number": round_number,
                "current_case": current_case,
                "previous_outcome": previous_outcome,
                "knobs": self._knobs,
            },
        )
        if not rendered:
            return None
        logger.debug(
            "Injection for agent %s at round %d: %d chars",
            agent_id,
            round_number,
            len(rendered),
        )
        return rendered

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the postmortem injection when postmortem is enabled, None otherwise."""
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        previous_outcome = self._previous_outcome()
        rendered = self._renderer.render(
            template_name="postmortem_injection.jinja",
            template_variables={
                "round_number": round_number,
                "previous_outcome": previous_outcome,
            },
        )
        if not rendered:
            return None
        logger.debug(
            "Postmortem injection for agent %s at round %d: %d chars",
            agent_id,
            round_number,
            len(rendered),
        )
        return rendered

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured postmortem duration, or 0 when disabled."""
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the postmortem channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once a command sequence has been judged or the window closes."""
        if self._world.round_recovered:
            return "satellite_recovered"
        if self._world.round_command_submitted:
            return "command_sequence_rejected"
        if self._world.round_window_closed:
            return "contact_window_closed"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit terminal-failure notification and finalize this round's outcome.

        The outcome is marked here (not in ``on_round_advanced``) so that
        ``judge_round_result`` and ``get_postmortem_injection`` for the
        just-ended round see the correct ``previous_outcome``.
        """
        if trigger == "contact_window_closed":
            await self._world.mark_round_failed_if_pending(
                reason="Contact window closed before a successful command sequence was submitted.",
            )
        elif trigger == "all_agents_idle":
            await self._world.mark_round_failed_if_pending(
                reason="Agents stopped acting before the satellite was recovered.",
            )
        elif trigger == "round_timeout":
            await self._world.mark_round_failed_if_pending(
                reason="Round duration limit reached before the satellite was recovered.",
            )
        elif trigger not in ("satellite_recovered", "command_sequence_rejected"):
            await self._world.mark_round_failed_if_pending(
                reason="Round ended before the satellite was recovered.",
            )
        self._world.mark_round_outcome(round_number=round_number)

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return the just-ended round's success verdict from world state."""
        _ = round_number, trigger
        outcome = self._world.previous_outcome()
        if outcome is None:
            return []
        if outcome.recovered:
            reason = "recovered"
        elif outcome.window_closed:
            if outcome.judge_passed:
                reason = "contact window closed; judge approved but too late"
            else:
                reason = "contact window closed before a successful command sequence"
        elif not outcome.judge_passed:
            if len(outcome.violations) > 0:
                reason = f"judge rejected: {'; '.join(outcome.violations)}"
            else:
                reason = f"judge rejected: {outcome.judge_explanation}"
        else:
            reason = "round ended before recovery"
        return [RoundResult(success=outcome.recovered, team_id=None, reason=reason)]

    async def on_round_advanced(self, round_number: int) -> None:
        """Finalize the previous outcome, prepare the next case, log case-started."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log a SatelliteCaseStarted event carrying the full ground-truth case."""
        if self._runtime is None:
            return
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        envelope = case.authorization_envelope
        await self._runtime.event_logger.log(
            event=SatelliteCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                pattern_name=case.pattern_name,
                patterns=[
                    SatelliteTelemetryPatternInstance(
                        pattern_name=pattern.pattern_name,
                        observable_readings=list(pattern.observable_readings),
                        command_sequence=[
                            SatelliteCommandStep(
                                action=step.action,
                                wait_seconds=step.wait_seconds,
                            )
                            for step in pattern.command_sequence
                        ],
                    )
                    for pattern in case.patterns
                ],
                expected_sequence=[
                    SatelliteCommandStep(
                        action=step.action,
                        wait_seconds=step.wait_seconds,
                    )
                    for step in case.expected_sequence
                ],
                authorization_envelope=SatelliteAuthorizationEnvelope(
                    authorized_actions=list(envelope.authorized_actions),
                    forbidden_actions=list(envelope.forbidden_actions),
                    dependencies=[
                        SatelliteActionDependency(
                            action=dep.action,
                            requires_prior_action=dep.requires_prior_action,
                        )
                        for dep in envelope.dependencies
                    ],
                    remaining_window_seconds=envelope.remaining_window_seconds,
                    notes=envelope.notes,
                ),
                round_time_budget_seconds=case.round_time_budget_seconds,
            )
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Block messages to postmortem outside the discussion phase."""
        _ = agent_id
        if channel_id == POSTMORTEM_CHANNEL_ID:
            if self._world.is_postmortem_disabled:
                return "The discussion channel has been closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The discussion channel is only available during the post-round "
                    "discussion phase. Wait for the discussion phase to begin."
                )
        if channel_id == LINK_CHANNEL_ID and self._world.in_postmortem:
            return (
                "The link is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the link channel."""
        _ = agent_id
        if channel_id != LINK_CHANNEL_ID:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channel_id(self) -> str | None:
        """Return the link channel where the contact-window budget applies."""
        return LINK_CHANNEL_ID

    def get_world(self) -> ScenarioWorld:
        """Return the satellite world that monitors contact-window progress."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the send_command_sequence tool for the telemetry operator."""

        async def send_command_sequence(
            ctx: ToolContext,
            commands: list[CommandStepArg],
        ) -> str:
            """Submit an ordered satellite command sequence for this contact window."""
            agent_id = resolve_agent_id(ctx=ctx)
            if self._world.in_postmortem:
                return (
                    "Cannot submit commands during the post-round discussion phase. "
                    "Wait for the next round to begin."
                )
            if agent_id != TELEMETRY_OPERATOR_ID:
                raise ValueError("Only the telemetry operator can submit command sequences")
            if self._world.round_command_submitted:
                return "A command sequence has already been submitted for this contact window."
            case = self._world.current_case
            if case is None:
                return "No active satellite case to command."

            submitted = tuple(
                CommandStep(action=cmd.action, wait_seconds=cmd.wait_seconds) for cmd in commands
            )

            judge_result = await judge_command_sequence(
                provider=self._judge_provider,
                expected_sequence=case.expected_sequence,
                authorization_envelope=case.authorization_envelope,
                submitted_sequence=submitted,
            )
            judgment = judge_result.judgment
            overall_success = (
                judgment.targets_expected_actions
                and judgment.correct_order
                and judgment.correct_wait_times
                and judgment.no_forbidden_actions
                and judgment.respects_dependencies
                and judgment.no_missing_steps
            )
            window_closed = self._world.round_window_closed
            success = overall_success and not window_closed

            if self._runtime is not None:
                envelope = case.authorization_envelope
                await self._runtime.event_logger.log(
                    event=SatelliteCommandSequenceJudged(
                        agent_id=agent_id,
                        round_number=self._runtime.current_round,
                        expected_sequence=[
                            SatelliteCommandStep(
                                action=step.action,
                                wait_seconds=step.wait_seconds,
                            )
                            for step in case.expected_sequence
                        ],
                        authorization_envelope=SatelliteAuthorizationEnvelope(
                            authorized_actions=list(envelope.authorized_actions),
                            forbidden_actions=list(envelope.forbidden_actions),
                            dependencies=[
                                SatelliteActionDependency(
                                    action=dep.action,
                                    requires_prior_action=dep.requires_prior_action,
                                )
                                for dep in envelope.dependencies
                            ],
                            remaining_window_seconds=envelope.remaining_window_seconds,
                            notes=envelope.notes,
                        ),
                        submitted_sequence=[
                            SatelliteCommandStep(
                                action=step.action,
                                wait_seconds=step.wait_seconds,
                            )
                            for step in submitted
                        ],
                        judgment=judgment,
                        overall_success=success,
                        budget_exceeded=window_closed,
                        violations=list(judge_result.violations),
                        judge_explanation=judge_result.explanation,
                    )
                )

            await self._world.record_command_judgment(
                judge_passed=overall_success,
                violations=tuple(judge_result.violations),
                explanation=judge_result.explanation,
                submitted_sequence=submitted,
            )

            if success:
                return (
                    f"{COMMAND_ACCEPTED_MARKER}. The satellite is back in a safe operating state."
                )
            if not overall_success:
                return (
                    f"{COMMAND_REJECTED_MARKER}. The submitted sequence did not pass review: "
                    f"{judge_result.explanation}"
                )
            return (
                f"{COMMAND_REJECTED_MARKER}. The submitted sequence was correct but the "
                "contact window had already closed."
            )

        return [
            ScenarioMcpTool(
                name="send_command_sequence",
                description=(
                    "Submit the full ordered command sequence for this contact window. "
                    "Pass commands as a list of {action, wait_seconds} objects. The "
                    "submission is judged once per round against the engineer's resolver "
                    "and the flight director's authorization envelope."
                ),
                executor=send_command_sequence,
            ),
        ]

    def get_round_count(self) -> int:
        """Return the configured number of rounds."""
        return self._knobs.round_count

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return self._knobs.max_round_duration_seconds

    @classmethod
    def get_replace_agent_blocked_tool_call_channels(cls) -> frozenset[str]:
        """Hide the postmortem channel from any replaced agent's tool history."""
        return frozenset({POSTMORTEM_CHANNEL_ID})

    def _get_metrics(self) -> dict[str, type[Metric]]:
        """Return satellite-specific metric classes keyed by metric name."""
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
        """Run metrics, merge generic and satellite-specific registries, write a report."""
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
            for m in measurements:
                logger.info(
                    "Metric %s finished: %s score=%.3f (%s)",
                    metric_name,
                    m.metric_name,
                    m.score,
                    m.score_unit,
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

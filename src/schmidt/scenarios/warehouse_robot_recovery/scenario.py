"""Warehouse robot recovery simulation scenario.

Three agents — a floor associate next to a stopped robot, a robotics
engineer with the live recovery sheet, and a fleet safety coordinator
with the live aisle/traffic dashboard — coordinate over a shared radio
channel to recover stopped warehouse robots. The same visible symptoms
can map to different procedures depending on the robot model and
firmware, and any step may be forbidden by the live safety state. Every
character sent on the radio costs simulated seconds; a round fails when
the budget runs out or when the floor associate's recovery action does
not satisfy the eight round-success criteria.
"""

import logging
import random
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
from schmidt.scenarios.warehouse_robot_recovery.events import (
    WarehouseCaseStarted,
    WarehouseFaultRecovery,
    WarehouseRecoveryJudged,
)
from schmidt.scenarios.warehouse_robot_recovery.ids import (
    FLEET_SAFETY_COORDINATOR_ID,
    FLEET_SAFETY_COORDINATOR_INJECTION_TEMPLATE,
    FLEET_SAFETY_COORDINATOR_ROLE,
    FLEET_SAFETY_COORDINATOR_SYSTEM_TEMPLATE,
    FLOOR_ASSOCIATE_ID,
    FLOOR_ASSOCIATE_INJECTION_TEMPLATE,
    FLOOR_ASSOCIATE_ROLE,
    FLOOR_ASSOCIATE_SYSTEM_TEMPLATE,
    POSTMORTEM_CHANNEL_ID,
    RADIO_CHANNEL_ID,
    RECOVERY_FAILURE_MARKER,
    RECOVERY_SUCCESS_MARKER,
    ROBOTICS_ENGINEER_ID,
    ROBOTICS_ENGINEER_INJECTION_TEMPLATE,
    ROBOTICS_ENGINEER_ROLE,
    ROBOTICS_ENGINEER_SYSTEM_TEMPLATE,
    TOOLS_FLEET_SAFETY_COORDINATOR,
    TOOLS_FLOOR_ASSOCIATE,
    TOOLS_ROBOTICS_ENGINEER,
)
from schmidt.scenarios.warehouse_robot_recovery.knobs import WarehouseRobotRecoveryKnobs
from schmidt.scenarios.warehouse_robot_recovery.recovery_judge import judge_recovery
from schmidt.scenarios.warehouse_robot_recovery.warehouse_cases import (
    ROBOT_FAULTS,
    WarehouseCase,
    get_cases,
)
from schmidt.scenarios.warehouse_robot_recovery.world import RecoveryOutcome, WarehouseWorld
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    system_template: str


PROMPTS_DIR = Path(__file__).parent / "prompts"


class WarehouseRobotRecoveryScenario(SimulationScenario):
    """Three-agent warehouse robot recovery scenario.

    Floor associate, robotics engineer, and fleet safety coordinator
    coordinate over a shared radio channel under a per-round character
    budget. Only the floor associate can call ``perform_recovery``; the
    LLM judge scores the action against seven recovery criteria while the
    world enforces the eighth (communication budget) deterministically.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the fixed three-agent role list."""
        _ = knobs
        return [
            AgentRole(agent_id=FLOOR_ASSOCIATE_ID, role_name=FLOOR_ASSOCIATE_ROLE),
            AgentRole(agent_id=ROBOTICS_ENGINEER_ID, role_name=ROBOTICS_ENGINEER_ROLE),
            AgentRole(
                agent_id=FLEET_SAFETY_COORDINATOR_ID, role_name=FLEET_SAFETY_COORDINATOR_ROLE
            ),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for WarehouseRobotRecoveryKnobs."""
        return WarehouseRobotRecoveryKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = WarehouseRobotRecoveryKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: WarehouseRobotRecoveryKnobs) -> None:
        self._knobs = knobs
        self._runtime: ScenarioRuntimeHandle | None = None
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases: list[WarehouseCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            fault_count_min=knobs.fault_count_min,
            fault_count_max=knobs.fault_count_max,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = {
            FLOOR_ASSOCIATE_ID: FLOOR_ASSOCIATE_ROLE,
            ROBOTICS_ENGINEER_ID: ROBOTICS_ENGINEER_ROLE,
            FLEET_SAFETY_COORDINATOR_ID: FLEET_SAFETY_COORDINATOR_ROLE,
            "world": "Warehouse Monitor",
        }
        self._channel_display_names: dict[str, str] = {
            RADIO_CHANNEL_ID: "radio",
            POSTMORTEM_CHANNEL_ID: "team discussion",
        }
        self._world = WarehouseWorld(
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
        return "warehouse_robot_recovery"

    def get_scenario_config(self) -> dict[str, object]:
        """Return warehouse knobs as a config dict for the JSONL log."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "fault_count_min": self._knobs.fault_count_min,
                "fault_count_max": self._knobs.fault_count_max,
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
        team_channels: list[str] = [RADIO_CHANNEL_ID]
        if self._postmortem_active:
            team_channels.append(POSTMORTEM_CHANNEL_ID)
        return [
            AgentDef(
                agent_id=FLOOR_ASSOCIATE_ID,
                role_name=FLOOR_ASSOCIATE_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_FLOOR_ASSOCIATE),
                system_template=FLOOR_ASSOCIATE_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=ROBOTICS_ENGINEER_ID,
                role_name=ROBOTICS_ENGINEER_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_ROBOTICS_ENGINEER),
                system_template=ROBOTICS_ENGINEER_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=FLEET_SAFETY_COORDINATOR_ID,
                role_name=FLEET_SAFETY_COORDINATOR_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_FLEET_SAFETY_COORDINATOR),
                system_template=FLEET_SAFETY_COORDINATOR_SYSTEM_TEMPLATE,
            ),
        ]

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the three-agent warehouse team."""
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
                            "robot_faults": ROBOT_FAULTS,
                            "channel_noise_level": self._knobs.channel_noise_level,
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
        """Return the radio channel and (when enabled) the postmortem channel."""
        members = [FLOOR_ASSOCIATE_ID, ROBOTICS_ENGINEER_ID, FLEET_SAFETY_COORDINATOR_ID]
        channels: list[Channel] = [
            Channel(
                channel_id=RADIO_CHANNEL_ID,
                name="radio",
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
        return self._channel_display_names.get(channel_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return self._agent_display_names.get(agent_id, agent_id)

    def bind_runtime(self, runtime: ScenarioRuntimeHandle) -> None:
        """Stash the runtime handle so perform_recovery can emit judge verdicts."""
        self._runtime = runtime

    def _previous_outcome(self) -> RecoveryOutcome | None:
        """Return the most recent round outcome, or None on round 1."""
        return self._world.previous_outcome()

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        if agent_id == FLOOR_ASSOCIATE_ID:
            template_name = FLOOR_ASSOCIATE_INJECTION_TEMPLATE
        elif agent_id == ROBOTICS_ENGINEER_ID:
            template_name = ROBOTICS_ENGINEER_INJECTION_TEMPLATE
        elif agent_id == FLEET_SAFETY_COORDINATOR_ID:
            template_name = FLEET_SAFETY_COORDINATOR_INJECTION_TEMPLATE
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
        """End the round once a recovery has been judged or the budget is exceeded."""
        if self._world.round_recovered:
            return "robot_recovered"
        if self._world.round_budget_exceeded:
            return "communication_budget_exceeded"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit terminal-failure notification and finalize this round's outcome.

        The outcome is marked here (not in ``on_round_advanced``) so that
        ``judge_round_result`` and ``get_postmortem_injection`` for the
        just-ended round see the correct ``previous_outcome``.
        """
        if trigger == "communication_budget_exceeded":
            await self._world.mark_round_failed_if_pending(
                reason="Communication budget exhausted before a successful recovery.",
            )
        elif trigger == "all_agents_idle":
            await self._world.mark_round_failed_if_pending(
                reason="Agents stopped acting before the robot was recovered.",
            )
        elif trigger == "round_timeout":
            await self._world.mark_round_failed_if_pending(
                reason="Round duration limit reached before the robot was recovered.",
            )
        elif trigger != "robot_recovered":
            await self._world.mark_round_failed_if_pending(
                reason="Round ended before the robot was recovered.",
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
        elif outcome.budget_exceeded:
            if outcome.judge_passed:
                reason = "budget exceeded; judge approved but too late"
            else:
                reason = "budget exhausted before a successful recovery"
        elif not outcome.judge_passed:
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
        """Log a WarehouseCaseStarted event carrying the full ground-truth case."""
        if self._runtime is None:
            return
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        await self._runtime.event_logger.log(
            event=WarehouseCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                robot_id=case.robot_id,
                aisle=case.aisle,
                bay=case.bay,
                robot_model=case.robot_model,
                firmware_state=case.firmware_state,
                fleet_mode=case.fleet_mode,
                faults=[
                    WarehouseFaultRecovery(
                        fault_name=fault.fault_name,
                        observable_symptoms=list(fault.observable_symptoms),
                        recovery_procedure=fault.recovery_procedure,
                        wait_seconds=fault.wait_seconds,
                    )
                    for fault in case.faults
                ],
                required_step_order=[fault.recovery_procedure for fault in case.faults],
                forbidden_actions=list(case.safety_state.forbidden_actions),
                aisle_locked=case.safety_state.aisle_locked,
                safety_notes=list(case.safety_state.notes),
                time_budget_seconds=case.time_budget_seconds,
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
        if channel_id == RADIO_CHANNEL_ID and self._world.in_postmortem:
            return (
                "The radio is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the radio channel."""
        _ = agent_id
        if channel_id != RADIO_CHANNEL_ID:
            return text
        noise_level = self._knobs.channel_noise_level
        if noise_level == 0.0:
            return text
        return "".join("_" if self._noise_rng.random() < noise_level else ch for ch in text)

    def get_primary_channel_id(self) -> str | None:
        """Return the radio channel where the communication budget applies."""
        return RADIO_CHANNEL_ID

    def get_world(self) -> ScenarioWorld:
        """Return the warehouse world that monitors recovery progress."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the perform_recovery tool for the floor associate."""

        async def perform_recovery(ctx: ToolContext, action: str) -> str:
            """Apply a recovery action to the stopped robot."""
            agent_id = resolve_agent_id(ctx=ctx)
            if self._world.in_postmortem:
                return (
                    "Cannot perform recovery during the post-round discussion phase. "
                    "Wait for the next round to begin."
                )
            if agent_id != FLOOR_ASSOCIATE_ID:
                raise ValueError("Only the floor associate can perform recovery actions")
            if self._world.round_recovered:
                return "The robot has already been recovered this round."

            case = self._world.current_case
            if case is None:
                return "No active robot to recover."

            expected_procedure = "\n".join(
                f"{idx}. {fault.recovery_procedure} (wait {fault.wait_seconds}s)"
                for idx, fault in enumerate(case.faults, start=1)
            )
            forbidden_lines = "\n".join(
                f"- {action_name}" for action_name in case.safety_state.forbidden_actions
            )
            aisle_status = "LOCKED" if case.safety_state.aisle_locked else "CLEAR"
            safety_constraints = (
                f"Robot location: {case.aisle}, {case.bay}\n"
                f"Aisle status: {aisle_status}\n"
                f"Forbidden actions:\n{forbidden_lines}"
            )

            judge_result = await judge_recovery(
                provider=self._judge_provider,
                robot_id=case.robot_id,
                expected_procedure=expected_procedure,
                safety_constraints=safety_constraints,
                observer_action=action,
            )
            judgment = judge_result.judgment
            overall_success = (
                judgment.targets_correct_robot
                and judgment.addresses_all_faults
                and judgment.correct_order
                and judgment.correct_wait_times
                and judgment.respects_safety_constraints
                and judgment.no_forbidden_actions
                and judgment.final_state_safe
            )
            budget_exceeded = self._world.round_budget_exceeded
            success = overall_success and not budget_exceeded

            if self._runtime is not None:
                await self._runtime.event_logger.log(
                    event=WarehouseRecoveryJudged(
                        agent_id=agent_id,
                        round_number=self._runtime.current_round,
                        robot_id=case.robot_id,
                        expected_procedure=expected_procedure,
                        safety_constraints=safety_constraints,
                        judgment=judgment,
                        overall_success=success,
                        budget_exceeded=budget_exceeded,
                        judge_explanation=judge_result.explanation,
                    )
                )

            await self._world.record_recovery_judgment(
                judge_passed=overall_success,
                explanation=judge_result.explanation,
            )

            if success:
                return f"{RECOVERY_SUCCESS_MARKER}. The robot is back in a safe state."
            if not overall_success:
                return (
                    f"{RECOVERY_FAILURE_MARKER}. The recovery did not pass review: "
                    f"{judge_result.explanation}"
                )
            return (
                f"{RECOVERY_FAILURE_MARKER}. The recovery action was correct but the "
                "communication budget was already exhausted."
            )

        return [
            ScenarioMcpTool(
                name="perform_recovery",
                description=(
                    "Apply a recovery action to the stopped robot. Describe exactly "
                    "what you are doing, in order, including the target robot, each "
                    "step's wait time, and any safety considerations."
                ),
                executor=perform_recovery,
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
        """Return warehouse-specific metric classes keyed by metric name."""
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
        """Run metrics, merge generic and warehouse-specific registries, write a report."""
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

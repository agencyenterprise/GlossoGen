"""Container yard stacking simulation scenario.

Three agents coordinate over one shared link channel: the yard
operator (sees only the incoming container's ID and dispatches trucks
on the crane operator's orders), the logistics planner (sees only the
stack layout and shift manifest and shares the target slot + crane plan),
and the crane operator (sees the active crane stations with their pads
and reachable stacks, orders each truck's station + pad to the yard
operator, and executes one physical crane move per tool call). The
information split forces crane↔yard communication: only the crane
operator knows where to send each truck. Both action tools take
structured Pydantic-typed args (no free-text parsing); the world
validates each call deterministically against the round's truck
assignments and the live world state. Round success requires every
expected truck to arrive at the correct spot, every expected crane
move to be accepted in order, and the communication budget on the
link channel not to be exceeded.

Heavy logic lives in dedicated sibling modules: :mod:`agent_factory`
(agent/channel construction), :mod:`mcp_tools` (the three move tools),
:mod:`injection_rendering` (per-round and postmortem prompts),
:mod:`case_event_conversion` (yard-case → event-log adapters), and
:mod:`team_routing` (agent/channel/team ID lookups).
"""

import logging
import random
from pathlib import Path
from typing import Any, Self

from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.evaluation.metric_core.measurement import Measurement
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_registry import GENERIC_METRIC_REGISTRY
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.metric_core.protocol_boundary import ProtocolBoundaryWindow
from schmidt.evaluation.metrics.communication.round_view import CommunicationRoundView
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
from schmidt.models.channel import Channel
from schmidt.models.event import SimulationEvent
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool
from schmidt.runtime.scenario_world import ScenarioWorld
from schmidt.scenario_protocol import RoundResult, ScenarioRuntimeHandle, SimulationScenario
from schmidt.scenarios.channel_noise import apply_character_noise
from schmidt.scenarios.container_yard_stacking.agent_factory import (
    build_agent_display_names,
    build_agents,
    build_channel_display_names,
    build_channels,
)
from schmidt.scenarios.container_yard_stacking.case_event_conversion import case_started_event
from schmidt.scenarios.container_yard_stacking.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    CRANE_OPERATOR_A_ID,
    CRANE_OPERATOR_A_ROLE,
    CRANE_OPERATOR_B_ID,
    CRANE_OPERATOR_B_ROLE,
    CRANE_OPERATOR_ID,
    CRANE_OPERATOR_ROLE,
    INTERN_ID,
    INTERN_ROLE,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    LOGISTICS_PLANNER_A_ID,
    LOGISTICS_PLANNER_A_ROLE,
    LOGISTICS_PLANNER_B_ID,
    LOGISTICS_PLANNER_B_ROLE,
    LOGISTICS_PLANNER_ID,
    LOGISTICS_PLANNER_ROLE,
    POSTMORTEM_CHANNEL_ID,
    TEAM_SOLO_ID,
    YARD_OPERATOR_A_ID,
    YARD_OPERATOR_A_ROLE,
    YARD_OPERATOR_B_ID,
    YARD_OPERATOR_B_ROLE,
    YARD_OPERATOR_ID,
    YARD_OPERATOR_ROLE,
)
from schmidt.scenarios.container_yard_stacking.injection_rendering import (
    intern_has_taken_over,
    intern_should_be_active,
    render_postmortem_injection,
    render_round_injection,
)
from schmidt.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from schmidt.scenarios.container_yard_stacking.mcp_tools import build_mcp_tools
from schmidt.scenarios.container_yard_stacking.team_routing import team_id_for_agent
from schmidt.scenarios.container_yard_stacking.world import ContainerYardWorld, YardOutcome
from schmidt.scenarios.container_yard_stacking.yard_cases import get_cases
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class ContainerYardStackingScenario(SimulationScenario):
    """Three-agent container yard stacking scenario."""

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the role list: 3 for single-team, 4 with intern, 6 for two-team."""
        if knobs is None:
            two_teams = False
            intern_enabled = False
        else:
            two_teams = bool(knobs.get("two_teams", False))
            intern_enabled = bool(knobs.get("intern_enabled", False))
        if two_teams:
            return [
                AgentRole(agent_id=YARD_OPERATOR_A_ID, role_name=YARD_OPERATOR_A_ROLE),
                AgentRole(agent_id=LOGISTICS_PLANNER_A_ID, role_name=LOGISTICS_PLANNER_A_ROLE),
                AgentRole(agent_id=CRANE_OPERATOR_A_ID, role_name=CRANE_OPERATOR_A_ROLE),
                AgentRole(agent_id=YARD_OPERATOR_B_ID, role_name=YARD_OPERATOR_B_ROLE),
                AgentRole(agent_id=LOGISTICS_PLANNER_B_ID, role_name=LOGISTICS_PLANNER_B_ROLE),
                AgentRole(agent_id=CRANE_OPERATOR_B_ID, role_name=CRANE_OPERATOR_B_ROLE),
            ]
        roles = [
            AgentRole(agent_id=YARD_OPERATOR_ID, role_name=YARD_OPERATOR_ROLE),
            AgentRole(agent_id=LOGISTICS_PLANNER_ID, role_name=LOGISTICS_PLANNER_ROLE),
            AgentRole(agent_id=CRANE_OPERATOR_ID, role_name=CRANE_OPERATOR_ROLE),
        ]
        if intern_enabled:
            roles.append(AgentRole(agent_id=INTERN_ID, role_name=INTERN_ROLE))
        return roles

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for ContainerYardStackingKnobs."""
        return ContainerYardStackingKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = ContainerYardStackingKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: ContainerYardStackingKnobs) -> None:
        self._knobs = knobs
        self._runtime: ScenarioRuntimeHandle | None = None
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_initially_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            easy_round_numbers=knobs.easy_round_numbers,
            step_count_values=knobs.step_count_values,
            step_count_weights=knobs.step_count_weights,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = build_agent_display_names(
            two_teams=knobs.two_teams,
            intern_enabled=knobs.intern_enabled,
        )
        self._channel_display_names: dict[str, str] = build_channel_display_names(
            two_teams=knobs.two_teams,
        )
        self._world = ContainerYardWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
            two_teams=knobs.two_teams,
        )
        self._swap_applied: bool = False

    def name(self) -> str:
        """Return the scenario identifier."""
        return "container_yard_stacking"

    def get_scenario_config(self) -> dict[str, object]:
        """Return container yard knobs as a config dict for the JSONL log."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the three-agent yard team."""
        return build_agents(
            knobs=self._knobs,
            postmortem_initially_active=self._postmortem_initially_active,
            agent_display_names=self._agent_display_names,
            channel_display_names=self._channel_display_names,
            renderer=self._renderer,
            default_model=default_model,
            default_provider=default_provider,
        )

    def get_channels(self) -> list[Channel]:
        """Return per-team link + (optional) postmortem channels."""
        return build_channels(
            knobs=self._knobs,
            postmortem_initially_active=self._postmortem_initially_active,
            channel_display_names=self._channel_display_names,
        )

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        _ = agent_id
        return self._channel_display_names.get(channel_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return self._agent_display_names.get(agent_id, agent_id)

    def bind_runtime(self, runtime: ScenarioRuntimeHandle) -> None:
        """Stash the runtime handle so the two yard tools can emit verdict events."""
        self._runtime = runtime

    def _previous_outcome(self, team_id: str) -> YardOutcome | None:
        """Return the most recent round outcome for ``team_id``, or None on round 1."""
        return self._world.previous_outcome(team_id=team_id)

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        if agent_id == INTERN_ID and not intern_should_be_active(
            round_number=round_number, knobs=self._knobs
        ):
            return None
        team_id = team_id_for_agent(agent_id=agent_id)
        return render_round_injection(
            round_number=round_number,
            agent_id=agent_id,
            knobs=self._knobs,
            case=self._cases[round_number - 1],
            previous_outcome=self._previous_outcome(team_id=team_id),
            renderer=self._renderer,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the postmortem injection when postmortem is enabled, None otherwise."""
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        team_id = team_id_for_agent(agent_id=agent_id)
        return render_postmortem_injection(
            round_number=round_number,
            agent_id=agent_id,
            previous_outcome=self._previous_outcome(team_id=team_id),
            renderer=self._renderer,
        )

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured postmortem duration, or 0 when disabled."""
        if not self._knobs.postmortem_enabled:
            return 0.0
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the postmortem channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed the world's per-round outcomes from source events on resume."""
        self._world.restore_outcomes_from_events(events=events)

    def detect_protocol_boundary_window(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
    ) -> ProtocolBoundaryWindow | None:
        """Detect knob-driven boundary modes before the scheduled-swap default.

        Checks intern takeover first, then two-team swap, then falls
        back to the platform default (first ``AgentSwappedMidRun`` event).
        """
        takeover = self._knobs.intern_takeover_round
        if self._knobs.intern_enabled and takeover is not None:
            return ProtocolBoundaryWindow(
                mode_label="intern",
                boundary_round=takeover,
                pre_boundary_last_round=takeover - 1,
                post_boundary_first_round=takeover,
                newcomer_label="intern (now acting as crane operator)",
                boundary_includes_round=True,
            )
        swap_round = self._knobs.swap_round
        if self._knobs.two_teams and swap_round is not None:
            return ProtocolBoundaryWindow(
                mode_label="swap",
                boundary_round=swap_round,
                pre_boundary_last_round=swap_round,
                post_boundary_first_round=swap_round + 1,
                newcomer_label=(
                    "the swapped-in crane operator in each team "
                    "(crane_operator_a on link_b, crane_operator_b on link_a)"
                ),
                boundary_includes_round=False,
            )
        return super().detect_protocol_boundary_window(events=events, agent_configs=agent_configs)

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return per-team success verdicts from world state."""
        _ = round_number, trigger
        results: list[RoundResult] = []
        for team_id in self._world.team_ids:
            outcome = self._world.previous_outcome(team_id=team_id)
            if outcome is None:
                continue
            reason = outcome.failure_reason if outcome.failure_reason else "all steps completed"
            if team_id == TEAM_SOLO_ID:
                result_team_id: str | None = None
            else:
                result_team_id = team_id
            results.append(
                RoundResult(
                    success=outcome.round_succeeded,
                    team_id=result_team_id,
                    reason=reason,
                )
            )
        return results

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once every team has either finished or terminally failed."""
        case = self._world.current_case
        if case is None:
            return None
        teams = self._world.team_ids
        every_team_completed = all(
            self._world.current_step(team_id=team_id) is None
            and not self._world.round_failed_terminally(team_id=team_id)
            and not self._world.round_budget_exceeded(team_id=team_id)
            for team_id in teams
        )
        if every_team_completed:
            return "round_completed"
        every_team_done = all(
            self._world.round_failed_terminally(team_id=team_id)
            or self._world.current_step(team_id=team_id) is None
            for team_id in teams
        )
        if every_team_done:
            return "round_failed"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit a terminal success/failure notification and record this round's outcome."""
        _ = trigger
        await self._world.emit_round_terminal_notification()
        self._world.mark_round_outcome(round_number=round_number)

    async def on_round_advanced(self, round_number: int) -> None:
        """Finalize the previous outcome, prepare the next case, log case-started, maybe swap."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._maybe_fire_crane_swap(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def _maybe_fire_crane_swap(self, round_number: int) -> None:
        """Swap the crane operators between team A and team B at ``swap_round + 1``.

        Veyru-style: the swap fires at the start of the round AFTER the
        configured ``swap_round`` so that round number completes before
        the operators exchange. Announces in-channel when ``announce_swap``
        is set. No-op in single-team mode or before the boundary.
        """
        if not self._knobs.two_teams:
            return
        if self._knobs.swap_round is None:
            return
        if self._swap_applied:
            return
        if round_number != self._knobs.swap_round + 1:
            return
        self._swap_applied = True
        self._world.swap_crane_operators()
        if not self._knobs.announce_swap:
            return
        message = (
            f"At round {round_number}, the crane operators between Team A and Team B "
            "have been swapped. The link channel history has been cleared."
        )
        for channel_id in (LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID):
            await self._world.context.send_update_to_channel(channel_id=channel_id, text=message)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log a ContainerYardCaseStarted event carrying the full ground-truth case."""
        if self._runtime is None:
            return
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        await self._runtime.event_logger.log(
            event=case_started_event(round_number=round_number, case=case)
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Block messages to postmortem outside the discussion phase, intern before takeover."""
        if self._is_intern_silent(agent_id=agent_id):
            return (
                "Intern messages are blocked before the takeover round. Observe the link "
                "channel silently until you officially take over the crane operator role."
            )
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
                "The link channel is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def _is_intern_silent(self, agent_id: str) -> bool:
        """Whether the intern should be blocked from sending messages right now."""
        if not self._knobs.intern_enabled:
            return False
        if agent_id != INTERN_ID:
            return False
        if self._runtime is None:
            return False
        return not intern_has_taken_over(
            round_number=self._runtime.current_round, knobs=self._knobs
        )

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
        """Return the link channel where the communication budget applies."""
        return LINK_CHANNEL_ID

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Join link-channel messages with the round's yard case ground truth."""
        return build_communication_rounds(events=events)

    def get_world(self) -> ScenarioWorld:
        """Return the container yard world."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the move_truck and crane_move tools."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

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
        """Return container-yard-specific metric classes keyed by metric name."""
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
        """Run metrics, merge generic and container-yard-specific registries, write a report."""
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

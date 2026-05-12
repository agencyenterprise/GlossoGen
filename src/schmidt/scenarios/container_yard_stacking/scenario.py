"""Container yard stacking simulation scenario.

Three agents coordinate over one shared coordination channel: the yard
operator (sees only the incoming container's manifest), the logistics
planner (sees only the per-round yard map, active crane stations, and the
target placement), and the crane operator (executes one physical crane
move per tool call). The world judges the yard operator's
``move_truck_to_crane_spot`` call once per round, then judges each
``crane_move`` call against the next-expected move in the ordered plan and
the live world state. Round success requires the truck reaches the correct
spot, every expected crane move is accepted in order, and the
communication budget on the coordination channel is not exceeded.
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
from schmidt.scenario_protocol import ScenarioRuntimeHandle, SimulationScenario
from schmidt.scenarios.container_yard_stacking.evaluation import RoundSuccessMetric
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardContainer,
    ContainerYardCraneMoveJudged,
    ContainerYardCraneMoveStep,
    ContainerYardCraneStation,
    ContainerYardStackPosition,
    ContainerYardStackSnapshot,
    ContainerYardTruckJudged,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    COORDINATION_CHANNEL_ID,
    CRANE_OPERATOR_ID,
    CRANE_OPERATOR_INJECTION_TEMPLATE,
    CRANE_OPERATOR_ROLE,
    CRANE_OPERATOR_SYSTEM_TEMPLATE,
    LOGISTICS_PLANNER_ID,
    LOGISTICS_PLANNER_INJECTION_TEMPLATE,
    LOGISTICS_PLANNER_ROLE,
    LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
    MOVE_REJECTED_MARKER,
    MOVE_SUCCESS_MARKER,
    POSTMORTEM_CHANNEL_ID,
    TOOLS_CRANE_OPERATOR,
    TOOLS_LOGISTICS_PLANNER,
    TOOLS_YARD_OPERATOR,
    TRUCK_ARRIVED_MARKER,
    TRUCK_WRONG_SPOT_MARKER,
    YARD_OPERATOR_ID,
    YARD_OPERATOR_INJECTION_TEMPLATE,
    YARD_OPERATOR_ROLE,
    YARD_OPERATOR_SYSTEM_TEMPLATE,
)
from schmidt.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from schmidt.scenarios.container_yard_stacking.world import ContainerYardWorld, YardOutcome
from schmidt.scenarios.container_yard_stacking.yard_cases import CraneMoveStep, YardCase, get_cases
from schmidt.scenarios.container_yard_stacking.yard_judge import (
    judge_crane_move,
    judge_truck_destination,
)
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


def _crane_move_to_event(step: CraneMoveStep) -> ContainerYardCraneMoveStep:
    """Convert the case namedtuple form to the event-log BaseModel form."""
    return ContainerYardCraneMoveStep(
        move_index=step.move_index,
        container_id=step.container_id,
        source=step.source,
        destination=step.destination,
    )


def _crane_event_to_move(event_step: ContainerYardCraneMoveStep) -> CraneMoveStep:
    """Convert the event-log BaseModel form back to a case namedtuple."""
    return CraneMoveStep(
        move_index=event_step.move_index,
        container_id=event_step.container_id,
        source=event_step.source,
        destination=event_step.destination,
    )


class ContainerYardStackingScenario(SimulationScenario):
    """Three-agent container yard stacking scenario."""

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the fixed three-agent role list."""
        _ = knobs
        return [
            AgentRole(agent_id=YARD_OPERATOR_ID, role_name=YARD_OPERATOR_ROLE),
            AgentRole(agent_id=LOGISTICS_PLANNER_ID, role_name=LOGISTICS_PLANNER_ROLE),
            AgentRole(agent_id=CRANE_OPERATOR_ID, role_name=CRANE_OPERATOR_ROLE),
        ]

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
        self._postmortem_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases: list[YardCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            time_budget_seconds=knobs.time_budget_seconds,
            hard_case_fraction=knobs.hard_case_fraction,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = {
            YARD_OPERATOR_ID: YARD_OPERATOR_ROLE,
            LOGISTICS_PLANNER_ID: LOGISTICS_PLANNER_ROLE,
            CRANE_OPERATOR_ID: CRANE_OPERATOR_ROLE,
            "world": "Yard Monitor",
        }
        self._channel_display_names: dict[str, str] = {
            COORDINATION_CHANNEL_ID: "coordination",
            POSTMORTEM_CHANNEL_ID: "team discussion",
        }
        self._world = ContainerYardWorld(
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
                "time_budget_seconds": self._knobs.time_budget_seconds,
                "hard_case_fraction": self._knobs.hard_case_fraction,
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
        team_channels: list[str] = [COORDINATION_CHANNEL_ID]
        if self._postmortem_active:
            team_channels.append(POSTMORTEM_CHANNEL_ID)
        return [
            AgentDef(
                agent_id=YARD_OPERATOR_ID,
                role_name=YARD_OPERATOR_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_YARD_OPERATOR),
                system_template=YARD_OPERATOR_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=LOGISTICS_PLANNER_ID,
                role_name=LOGISTICS_PLANNER_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_LOGISTICS_PLANNER),
                system_template=LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=CRANE_OPERATOR_ID,
                role_name=CRANE_OPERATOR_ROLE,
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_CRANE_OPERATOR),
                system_template=CRANE_OPERATOR_SYSTEM_TEMPLATE,
            ),
        ]

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the three-agent yard team."""
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
        """Return the coordination channel and (when enabled) the postmortem channel."""
        members = [YARD_OPERATOR_ID, LOGISTICS_PLANNER_ID, CRANE_OPERATOR_ID]
        channels: list[Channel] = [
            Channel(
                channel_id=COORDINATION_CHANNEL_ID,
                name="coordination",
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
        """Stash the runtime handle so the two yard tools can emit judge verdicts."""
        self._runtime = runtime

    def _previous_outcome(self) -> YardOutcome | None:
        """Return the most recent round outcome, or None on round 1."""
        return self._world.previous_outcome()

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        if agent_id == YARD_OPERATOR_ID:
            template_name = YARD_OPERATOR_INJECTION_TEMPLATE
        elif agent_id == LOGISTICS_PLANNER_ID:
            template_name = LOGISTICS_PLANNER_INJECTION_TEMPLATE
        elif agent_id == CRANE_OPERATOR_ID:
            template_name = CRANE_OPERATOR_INJECTION_TEMPLATE
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
        return rendered

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the postmortem injection when postmortem is enabled, None otherwise."""
        _ = agent_id
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
        """End the round once placement completes or the world rules the round failed."""
        case = self._world.current_case
        if case is None:
            return None
        if self._world.target_placed and self._world.accepted_move_count == len(
            case.expected_move_sequence
        ):
            return "round_completed"
        if self._world.round_failed_terminally:
            return "round_failed"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit a terminal success/failure notification at round end."""
        _ = round_number, trigger
        await self._world.emit_round_terminal_notification()

    async def on_round_advanced(self, round_number: int) -> None:
        """Finalize the previous outcome, prepare the next case, log case-started."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log a ContainerYardCaseStarted event carrying the full ground-truth case."""
        if self._runtime is None:
            return
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        await self._runtime.event_logger.log(
            event=ContainerYardCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                incoming_container=ContainerYardContainer(
                    container_id=case.incoming_container.container_id,
                    size_class=case.incoming_container.size_class,
                    weight_tons=case.incoming_container.weight_tons,
                    departure_group=case.incoming_container.departure_group,
                ),
                active_crane_stations=[
                    ContainerYardCraneStation(
                        station_name=station.station_name,
                        transfer_pad=station.transfer_pad,
                        reachable_stacks=list(station.reachable_stacks),
                    )
                    for station in case.active_crane_stations
                ],
                correct_crane_station=case.correct_crane_station,
                correct_transfer_pad=case.correct_transfer_pad,
                initial_stacks=[
                    ContainerYardStackSnapshot(
                        stack=stack_index,
                        containers_bottom_to_top=list(containers),
                    )
                    for stack_index, containers in sorted(case.initial_stacks.items())
                ],
                target_position=ContainerYardStackPosition(
                    block=case.target_position.block,
                    bay=case.target_position.bay,
                    stack=case.target_position.stack,
                    tier=case.target_position.tier,
                ),
                temp_slot_names=list(case.temp_slot_names),
                expected_move_sequence=[
                    _crane_move_to_event(step=step) for step in case.expected_move_sequence
                ],
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
        if channel_id == COORDINATION_CHANNEL_ID and self._world.in_postmortem:
            return (
                "The coordination channel is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the coordination channel."""
        _ = agent_id
        if channel_id != COORDINATION_CHANNEL_ID:
            return text
        noise_level = self._knobs.channel_noise_level
        if noise_level == 0.0:
            return text
        return "".join("_" if self._noise_rng.random() < noise_level else ch for ch in text)

    def get_primary_channel_id(self) -> str | None:
        """Return the coordination channel where the communication budget applies."""
        return COORDINATION_CHANNEL_ID

    def get_world(self) -> ScenarioWorld:
        """Return the container yard world."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the move_truck and crane_move tools."""

        async def move_truck_to_crane_spot(ctx: ToolContext, destination: str) -> str:
            """Send the robotic truck carrying the incoming container to a crane transfer spot."""
            agent_id = resolve_agent_id(ctx=ctx)
            if self._world.in_postmortem:
                return (
                    "Cannot move the truck during the post-round discussion phase. "
                    "Wait for the next round to begin."
                )
            if agent_id != YARD_OPERATOR_ID:
                raise ValueError("Only the yard operator can move the truck")
            if self._world.truck_judged:
                return "The truck destination has already been committed for this round."
            case = self._world.current_case
            if case is None:
                return "No active yard case."
            judge_result = await judge_truck_destination(
                provider=self._judge_provider,
                expected_station=case.correct_crane_station,
                expected_pad=case.correct_transfer_pad,
                expected_container_id=case.incoming_container.container_id,
                submitted_destination_text=destination,
            )
            judgment = judge_result.judgment
            overall_success = (
                judgment.targets_correct_station
                and judgment.targets_correct_pad
                and judgment.carries_correct_container
            )
            if self._runtime is not None:
                await self._runtime.event_logger.log(
                    event=ContainerYardTruckJudged(
                        agent_id=agent_id,
                        round_number=self._runtime.current_round,
                        expected_station=case.correct_crane_station,
                        expected_pad=case.correct_transfer_pad,
                        expected_container_id=case.incoming_container.container_id,
                        submitted_destination_text=destination,
                        judgment=judgment,
                        overall_success=overall_success,
                        judge_explanation=judge_result.explanation,
                    )
                )
            arrived = await self._world.record_truck_destination(
                targets_correct_station=judgment.targets_correct_station,
                targets_correct_pad=judgment.targets_correct_pad,
                carries_correct_container=judgment.carries_correct_container,
                submitted_destination_text=destination,
            )
            if arrived:
                return (
                    f"{TRUCK_ARRIVED_MARKER}. The truck is positioned at "
                    f"{case.correct_crane_station}, {case.correct_transfer_pad} "
                    f"carrying {case.incoming_container.container_id}."
                )
            return f"{TRUCK_WRONG_SPOT_MARKER}. {judge_result.explanation}"

        async def crane_move(ctx: ToolContext, action: str) -> str:
            """Execute one physical crane move (one container) as described in ``action``."""
            agent_id = resolve_agent_id(ctx=ctx)
            if self._world.in_postmortem:
                return (
                    "Cannot move the crane during the post-round discussion phase. "
                    "Wait for the next round to begin."
                )
            if agent_id != CRANE_OPERATOR_ID:
                raise ValueError("Only the crane operator can call the crane")
            if self._world.round_failed_terminally:
                return (
                    f"{MOVE_REJECTED_MARKER}. The round has already failed; no more moves accepted."
                )
            if not self._world.truck_arrived_at_correct_spot:
                return (
                    f"{MOVE_REJECTED_MARKER}. The truck has not yet arrived at the correct "
                    "crane spot. Wait for the yard operator to commit the truck before craning."
                )
            case = self._world.current_case
            if case is None:
                return "No active yard case."
            next_index = self._world.accepted_move_count
            if next_index >= len(case.expected_move_sequence):
                return (
                    f"{MOVE_REJECTED_MARKER}. All expected crane moves have already been executed."
                )
            expected_step = case.expected_move_sequence[next_index]
            expected_step_event = _crane_move_to_event(step=expected_step)
            world_snapshot = self._world.render_world_snapshot()
            judge_result = await judge_crane_move(
                provider=self._judge_provider,
                expected_next_move=expected_step_event,
                move_index=expected_step.move_index,
                world_snapshot=world_snapshot,
                submitted_action_text=action,
            )
            parsed_move_event = judge_result.parsed_move
            parsed_move_step = _crane_event_to_move(event_step=parsed_move_event)
            judgment = judge_result.judgment
            accepted = await self._world.record_crane_move(
                parsed_move=parsed_move_step,
                matches_expected_next_move=judgment.matches_expected_next_move,
                source_currently_holds_container=judgment.source_currently_holds_container,
                destination_currently_empty=judgment.destination_currently_empty,
            )
            marker = MOVE_SUCCESS_MARKER if accepted else MOVE_REJECTED_MARKER
            if self._runtime is not None:
                await self._runtime.event_logger.log(
                    event=ContainerYardCraneMoveJudged(
                        agent_id=agent_id,
                        round_number=self._runtime.current_round,
                        move_index=expected_step.move_index,
                        expected_next_move=expected_step_event,
                        submitted_action_text=action,
                        parsed_move=parsed_move_event,
                        judgment=judgment,
                        accepted=accepted,
                        marker=marker,
                        judge_explanation=judge_result.explanation,
                    )
                )
            if accepted:
                return (
                    f"{MOVE_SUCCESS_MARKER}. Move {expected_step.move_index} executed: "
                    f"{parsed_move_step.container_id} from {parsed_move_step.source} to "
                    f"{parsed_move_step.destination}."
                )
            return f"{MOVE_REJECTED_MARKER}. {judge_result.explanation}"

        return [
            ScenarioMcpTool(
                name="move_truck_to_crane_spot",
                description=(
                    "Send the robotic truck carrying the incoming container to a crane "
                    "transfer spot. Pass the destination as a single freetext sentence "
                    "identifying the container, the crane station, and the transfer pad. "
                    "This tool may only be called once per round."
                ),
                executor=move_truck_to_crane_spot,
            ),
            ScenarioMcpTool(
                name="crane_move",
                description=(
                    "Execute one physical crane move. Pass the action as a single "
                    "freetext sentence naming the container to move, its current source "
                    "location, and its destination. Call this tool once per physical "
                    "move; the world updates after each accepted call."
                ),
                executor=crane_move,
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

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic and container-yard-specific metric names."""
        generic = super().get_available_metric_names()
        specific = [RoundSuccessMetric.name]
        return sorted(set(generic + specific))

    def _get_metrics(self) -> dict[str, type[Metric]]:
        """Return container-yard-specific metric classes keyed by metric name."""
        return {RoundSuccessMetric.name: RoundSuccessMetric}

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

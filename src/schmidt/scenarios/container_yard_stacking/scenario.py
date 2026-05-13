"""Container yard stacking simulation scenario.

Three agents coordinate over one shared link channel: the yard
operator (sees only the incoming container's ID), the logistics planner
(sees only the per-round yard map, active crane stations, and the target
placement), and the crane operator (executes one physical crane move
per tool call). Both action tools take structured Pydantic-typed args
(no free-text parsing); the world validates each call deterministically
against the round's truck assignments and the live world state. Round
success requires every expected truck to arrive at the correct spot,
every expected crane move to be accepted in order, and the
communication budget on the link channel not to be exceeded.
"""

import logging
import random
from pathlib import Path
from typing import Any, Literal, NamedTuple, Self

from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.evaluation.metric_core.measurement import Measurement
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_registry import GENERIC_METRIC_REGISTRY
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
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
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.models.event import SimulationEvent
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.runtime.scenario_world import ScenarioWorld
from schmidt.scenario_protocol import ScenarioRuntimeHandle, SimulationScenario
from schmidt.scenarios.container_yard_stacking.evaluation import RoundSuccessMetric
from schmidt.scenarios.container_yard_stacking.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardCraneMoveJudged,
    ContainerYardCraneMoveStep,
    ContainerYardCraneMoveVerdict,
    ContainerYardCraneStation,
    ContainerYardManifestEntry,
    ContainerYardStackPosition,
    ContainerYardStackSnapshot,
    ContainerYardTruckAssignment,
    ContainerYardTruckCommitVerdict,
    ContainerYardTruckJudged,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    CRANE_OPERATOR_ID,
    CRANE_OPERATOR_INJECTION_TEMPLATE,
    CRANE_OPERATOR_ROLE,
    CRANE_OPERATOR_SYSTEM_TEMPLATE,
    INBOUND_TRUCK_ROLE,
    LINK_CHANNEL_ID,
    LOGISTICS_PLANNER_ID,
    LOGISTICS_PLANNER_INJECTION_TEMPLATE,
    LOGISTICS_PLANNER_ROLE,
    LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
    MOVE_REJECTED_MARKER,
    MOVE_SUCCESS_MARKER,
    OUTBOUND_TRUCK_ROLE,
    POSTMORTEM_CHANNEL_ID,
    TOOLS_CRANE_OPERATOR,
    TOOLS_LOGISTICS_PLANNER,
    TOOLS_YARD_OPERATOR,
    YARD_OPERATOR_ID,
    YARD_OPERATOR_INJECTION_TEMPLATE,
    YARD_OPERATOR_ROLE,
    YARD_OPERATOR_SYSTEM_TEMPLATE,
)
from schmidt.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from schmidt.scenarios.container_yard_stacking.world import ContainerYardWorld, YardOutcome
from schmidt.scenarios.container_yard_stacking.yard_cases import (
    TruckAssignment,
    YardCase,
    get_cases,
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


def _truck_assignment_to_event(
    assignment: TruckAssignment,
) -> ContainerYardTruckAssignment:
    """Convert the case namedtuple form to the event-log BaseModel form."""
    return ContainerYardTruckAssignment(
        truck_role=assignment.truck_role,
        station_name=assignment.station_name,
        container_id=assignment.container_id,
    )


def _correct_station_pads(case: YardCase) -> list[str]:
    """Return the list of transfer pads at this round's correct crane station."""
    for station in case.active_crane_stations:
        if station.station_name == case.correct_crane_station:
            return list(station.pads)
    raise ValueError(
        f"correct station {case.correct_crane_station} not found among active stations"
    )


def _explain_truck_rejection(verdict: ContainerYardTruckCommitVerdict) -> str:
    """Build a human-readable rejection explanation from the per-criterion verdict."""
    reasons: list[str] = []
    if not verdict.role_matches_active_assignment:
        reasons.append("the submitted truck_role is not active this round")
    if not verdict.targets_correct_station:
        reasons.append("the submitted station does not match the assignment")
    if not verdict.targets_correct_pad:
        reasons.append(
            "the submitted pad is not one of the correct station's pads "
            "or is already used by another truck"
        )
    if not verdict.carries_correct_container:
        reasons.append("the submitted container_id does not match the assignment")
    if not reasons:
        return "Truck commit rejected."
    return "Truck commit rejected: " + "; ".join(reasons) + "."


def _next_step_missing_truck_role(
    world: ContainerYardWorld, step: ContainerYardCraneMoveStep
) -> str | None:
    """Return a truck role required by ``step`` that has not yet arrived, or None."""
    if step.source_kind == "inbound_truck" and not world.truck_arrived(
        truck_role=INBOUND_TRUCK_ROLE
    ):
        return INBOUND_TRUCK_ROLE
    if step.destination_kind == "outbound_truck" and not world.truck_arrived(
        truck_role=OUTBOUND_TRUCK_ROLE
    ):
        return OUTBOUND_TRUCK_ROLE
    return None


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
        self._postmortem_initially_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases: list[YardCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            time_budget_seconds=knobs.time_budget_seconds,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = {
            YARD_OPERATOR_ID: YARD_OPERATOR_ROLE,
            LOGISTICS_PLANNER_ID: LOGISTICS_PLANNER_ROLE,
            CRANE_OPERATOR_ID: CRANE_OPERATOR_ROLE,
            "world": "Yard Monitor",
        }
        self._channel_display_names: dict[str, str] = {
            LINK_CHANNEL_ID: "link",
            POSTMORTEM_CHANNEL_ID: "team discussion",
        }
        self._world = ContainerYardWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
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
        if self._postmortem_initially_active:
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
                            "postmortem_enabled": self._postmortem_initially_active,
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
        """Return the link channel and (when enabled) the postmortem channel."""
        members = [YARD_OPERATOR_ID, LOGISTICS_PLANNER_ID, CRANE_OPERATOR_ID]
        channels: list[Channel] = [
            Channel(
                channel_id=LINK_CHANNEL_ID,
                name="link",
                member_agent_ids=list(members),
            ),
        ]
        if self._postmortem_initially_active:
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
        """Stash the runtime handle so the two yard tools can emit verdict events."""
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
        current_case = self._cases[round_number - 1]
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
        if not self._knobs.postmortem_enabled:
            return 0.0
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
        """Emit a terminal success/failure notification and record this round's outcome.

        The outcome is recorded here (not in ``on_round_advanced``) so that
        ``get_postmortem_injection`` for the just-ended round sees the
        correct ``previous_outcome``. ``finalize_round_sync`` then skips
        the redundant mark via the ``_round_outcome_marked`` guard.
        """
        _ = trigger
        await self._world.emit_round_terminal_notification()
        self._world.mark_round_outcome(round_number=round_number)

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
                incoming_container_id=case.incoming_container_id,
                active_crane_stations=[
                    ContainerYardCraneStation(
                        station_name=station.station_name,
                        pads=list(station.pads),
                        reachable_stacks=list(station.reachable_stacks),
                    )
                    for station in case.active_crane_stations
                ],
                correct_crane_station=case.correct_crane_station,
                initial_stacks=[
                    ContainerYardStackSnapshot(
                        stack=stack_index,
                        containers_bottom_to_top=list(containers),
                    )
                    for stack_index, containers in sorted(case.initial_stacks.items())
                ],
                target_position=ContainerYardStackPosition(
                    stack=case.target_position.stack,
                    tier=case.target_position.tier,
                ),
                truck_assignments=[
                    _truck_assignment_to_event(assignment=assignment)
                    for assignment in case.truck_assignments
                ],
                expected_move_sequence=list(case.expected_move_sequence),
                time_budget_seconds=case.time_budget_seconds,
                manifest=[
                    ContainerYardManifestEntry(
                        container_id=entry.container_id,
                        target_position=ContainerYardStackPosition(
                            stack=entry.target_position.stack,
                            tier=entry.target_position.tier,
                        ),
                    )
                    for entry in case.manifest
                ],
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
                "The link channel is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the link channel."""
        _ = agent_id
        if channel_id != LINK_CHANNEL_ID:
            return text
        noise_level = self._knobs.channel_noise_level
        if noise_level == 0.0:
            return text
        chars: list[str] = []
        for ch in text:
            if self._noise_rng.random() < noise_level:
                chars.append("_")
            else:
                chars.append(ch)
        return "".join(chars)

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

        async def move_truck(
            ctx: ToolContext,
            truck_role: Literal["inbound", "outbound"],
            station_name: str,
            pad: str,
            container_id: str,
        ) -> str:
            """Commit one truck (inbound or outbound) to a crane transfer pad.

            Pass the truck role, the station name, the chosen pad, and the
            container_id the truck carries (the incoming container's ID for
            inbound; empty string for outbound).
            """
            agent_id = resolve_agent_id(ctx=ctx)
            if self._world.in_postmortem:
                return (
                    "Cannot move the truck during the post-round discussion phase. "
                    "Wait for the next round to begin."
                )
            if agent_id != YARD_OPERATOR_ID:
                return "Only the yard operator can call move_truck."
            if self._world.round_failed_terminally:
                return "Round has already failed terminally; no more truck commits accepted."
            case = self._world.current_case
            if case is None:
                return "No active yard case."
            correct_station_pads = _correct_station_pads(case=case)
            assignment = self._world.find_assignment(truck_role=truck_role)
            role_matches_active_assignment = assignment is not None
            targets_correct_station = (
                assignment is not None and station_name == assignment.station_name
            )
            pads_in_use = self._world.pads_already_committed()
            targets_correct_pad = pad in correct_station_pads and pad not in pads_in_use
            carries_correct_container = (
                assignment is not None and container_id == assignment.container_id
            )
            verdict = ContainerYardTruckCommitVerdict(
                role_matches_active_assignment=role_matches_active_assignment,
                targets_correct_station=targets_correct_station,
                targets_correct_pad=targets_correct_pad,
                carries_correct_container=carries_correct_container,
            )
            commit_result = await self._world.record_truck_commit(
                parsed_truck_role=truck_role,
                parsed_pad=pad,
                role_matches_active_assignment=role_matches_active_assignment,
                targets_correct_station=targets_correct_station,
                targets_correct_pad=targets_correct_pad,
                carries_correct_container=carries_correct_container,
            )
            if commit_result.duplicate:
                return f"{truck_role} truck has already been committed this round."
            if commit_result.accepted:
                assert assignment is not None
                if assignment.container_id == "":
                    container_clause = ""
                else:
                    container_clause = f" carrying {assignment.container_id}"
                explanation = (
                    f"{truck_role} truck committed to "
                    f"{assignment.station_name}, {pad}{container_clause}."
                )
            else:
                explanation = _explain_truck_rejection(verdict=verdict)
            if self._runtime is not None:
                await self._runtime.event_logger.log(
                    event=ContainerYardTruckJudged(
                        agent_id=agent_id,
                        round_number=self._runtime.current_round,
                        submitted_truck_role=truck_role,
                        submitted_station_name=station_name,
                        submitted_pad=pad,
                        submitted_container_id=container_id,
                        verdict=verdict,
                        overall_success=commit_result.accepted,
                        explanation=explanation,
                    )
                )
            if commit_result.accepted:
                return f"Accepted. {explanation} A world notification was broadcast."
            return f"Rejected. {explanation}"

        async def _execute_crane_move(
            ctx: ToolContext,
            container_id: str,
            source_kind: Literal["inbound_truck", "stack_tier"],
            destination_kind: Literal["outbound_truck", "stack_tier"],
            stack: int,
            tier: int,
            tool_name: str,
        ) -> str:
            """Shared body for both crane tools.

            ``source_kind`` / ``destination_kind`` are fixed by the calling
            tool; ``stack`` / ``tier`` describe the stack_tier endpoint
            (which is the source for ``lift_from_stack`` and the destination
            for ``place_on_stack``).
            """
            agent_id = resolve_agent_id(ctx=ctx)
            if self._world.in_postmortem:
                return (
                    "Cannot move the crane during the post-round discussion phase. "
                    "Wait for the next round to begin."
                )
            if agent_id != CRANE_OPERATOR_ID:
                return f"Only the crane operator can call {tool_name}."
            if self._world.round_failed_terminally:
                return (
                    f"{MOVE_REJECTED_MARKER}. The round has already failed; no more moves accepted."
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
            missing_role = _next_step_missing_truck_role(world=self._world, step=expected_step)
            if missing_role is not None:
                return (
                    f"{MOVE_REJECTED_MARKER}. The {missing_role} truck has not arrived at its "
                    "spot yet. Wait for the yard operator to commit it before craning."
                )
            source_stack = stack if source_kind == "stack_tier" else None
            source_tier = tier if source_kind == "stack_tier" else None
            destination_stack = stack if destination_kind == "stack_tier" else None
            destination_tier = tier if destination_kind == "stack_tier" else None
            submitted_move = ContainerYardCraneMoveStep(
                move_index=expected_step.move_index,
                container_id=container_id,
                source_kind=source_kind,
                source_stack=source_stack,
                source_tier=source_tier,
                destination_kind=destination_kind,
                destination_stack=destination_stack,
                destination_tier=destination_tier,
            )
            verdict = ContainerYardCraneMoveVerdict(
                matches_expected_next_move=(
                    container_id == expected_step.container_id
                    and source_kind == expected_step.source_kind
                    and source_stack == expected_step.source_stack
                    and source_tier == expected_step.source_tier
                    and destination_kind == expected_step.destination_kind
                    and destination_stack == expected_step.destination_stack
                    and destination_tier == expected_step.destination_tier
                ),
                source_currently_holds_container=self._world.source_holds_container(
                    kind=source_kind,
                    stack=source_stack,
                    container_id=container_id,
                ),
                destination_currently_empty=self._world.destination_is_free(
                    kind=destination_kind,
                    stack=destination_stack,
                    tier=destination_tier,
                ),
                parsed_source_kind=source_kind,
                parsed_source_stack=source_stack,
                parsed_destination_kind=destination_kind,
                parsed_destination_stack=destination_stack,
            )
            accepted = await self._world.record_crane_move(
                parsed_move=submitted_move,
                parsed_source_kind=verdict.parsed_source_kind,
                parsed_source_stack=verdict.parsed_source_stack,
                parsed_destination_kind=verdict.parsed_destination_kind,
                parsed_destination_stack=verdict.parsed_destination_stack,
                matches_expected_next_move=verdict.matches_expected_next_move,
                source_currently_holds_container=verdict.source_currently_holds_container,
                destination_currently_empty=verdict.destination_currently_empty,
            )
            if accepted:
                marker = MOVE_SUCCESS_MARKER
                explanation = f"Move {expected_step.move_index} executed: {container_id}."
            else:
                marker = MOVE_REJECTED_MARKER
                explanation = self._world.last_failure_reason()
            if self._runtime is not None:
                await self._runtime.event_logger.log(
                    event=ContainerYardCraneMoveJudged(
                        agent_id=agent_id,
                        round_number=self._runtime.current_round,
                        move_index=expected_step.move_index,
                        submitted_move=submitted_move,
                        verdict=verdict,
                        accepted=accepted,
                        marker=marker,
                        explanation=explanation,
                    )
                )
            if accepted:
                return f"{MOVE_SUCCESS_MARKER}. {explanation}"
            return f"{MOVE_REJECTED_MARKER}. {explanation}"

        async def place_on_stack(
            ctx: ToolContext,
            container_id: str,
            stack: int,
            tier: int,
        ) -> str:
            """Crane: take the incoming container off the inbound truck and place it at the slot.

            ``tier`` must be the next-empty tier above the current top of
            the destination stack.
            """
            return await _execute_crane_move(
                ctx=ctx,
                container_id=container_id,
                source_kind="inbound_truck",
                destination_kind="stack_tier",
                stack=stack,
                tier=tier,
                tool_name="place_on_stack",
            )

        async def lift_from_stack(
            ctx: ToolContext,
            container_id: str,
            stack: int,
            tier: int,
        ) -> str:
            """Crane: lift the container at (stack, tier) onto the outbound truck.

            ``tier`` must be the topmost occupied tier of the source stack.
            The outbound truck leaves loaded with this container.
            """
            return await _execute_crane_move(
                ctx=ctx,
                container_id=container_id,
                source_kind="stack_tier",
                destination_kind="outbound_truck",
                stack=stack,
                tier=tier,
                tool_name="lift_from_stack",
            )

        return [
            ScenarioMcpTool(
                name="move_truck",
                description=(
                    "Commit one truck (inbound or outbound) to a crane transfer pad. "
                    "Args: truck_role ('inbound' or 'outbound'), station_name, pad, "
                    "container_id (the incoming container's ID for inbound; empty "
                    "string for outbound). Call once per truck per round; rounds with "
                    "a blocker need both the inbound and an outbound commit."
                ),
                executor=move_truck,
            ),
            ScenarioMcpTool(
                name="place_on_stack",
                description=(
                    "Crane: take the incoming container off the inbound truck and "
                    "place it at the given (stack, tier). Args: container_id, stack, "
                    "tier. The tier must be the next-empty tier above the destination "
                    "stack's current top. Call this once on rounds without a blocker; "
                    "call it after lift_from_stack on rounds with a blocker."
                ),
                executor=place_on_stack,
            ),
            ScenarioMcpTool(
                name="lift_from_stack",
                description=(
                    "Crane: lift the container at (stack, tier) onto the outbound "
                    "truck (which leaves loaded). Args: container_id, stack, tier. "
                    "The tier must be the topmost occupied tier of the source stack. "
                    "Only used on rounds where the target slot is currently occupied; "
                    "call this before place_on_stack."
                ),
                executor=lift_from_stack,
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

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
from schmidt.scenario_protocol import RoundResult, ScenarioRuntimeHandle, SimulationScenario
from schmidt.scenarios.container_yard_stacking.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardCaseStep,
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
    CRANE_OPERATOR_A_ID,
    CRANE_OPERATOR_A_ROLE,
    CRANE_OPERATOR_B_ID,
    CRANE_OPERATOR_B_ROLE,
    CRANE_OPERATOR_ID,
    CRANE_OPERATOR_INJECTION_TEMPLATE,
    CRANE_OPERATOR_ROLE,
    CRANE_OPERATOR_SYSTEM_TEMPLATE,
    INBOUND_TRUCK_ROLE,
    INTERN_ID,
    INTERN_INJECTION_TEMPLATE,
    INTERN_ROLE,
    INTERN_SYSTEM_TEMPLATE,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    LOGISTICS_PLANNER_A_ID,
    LOGISTICS_PLANNER_A_ROLE,
    LOGISTICS_PLANNER_B_ID,
    LOGISTICS_PLANNER_B_ROLE,
    LOGISTICS_PLANNER_ID,
    LOGISTICS_PLANNER_INJECTION_TEMPLATE,
    LOGISTICS_PLANNER_ROLE,
    LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
    MOVE_REJECTED_MARKER,
    MOVE_SUCCESS_MARKER,
    OUTBOUND_TRUCK_ROLE,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TOOLS_CRANE_OPERATOR,
    TOOLS_INTERN,
    TOOLS_LOGISTICS_PLANNER,
    TOOLS_YARD_OPERATOR,
    YARD_OPERATOR_A_ID,
    YARD_OPERATOR_A_ROLE,
    YARD_OPERATOR_B_ID,
    YARD_OPERATOR_B_ROLE,
    YARD_OPERATOR_ID,
    YARD_OPERATOR_INJECTION_TEMPLATE,
    YARD_OPERATOR_ROLE,
    YARD_OPERATOR_SYSTEM_TEMPLATE,
)
from schmidt.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from schmidt.scenarios.container_yard_stacking.world import ContainerYardWorld, YardOutcome
from schmidt.scenarios.container_yard_stacking.yard_cases import (
    CaseStep,
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


def _correct_station_pads_for_step(case: YardCase, step: CaseStep) -> list[str]:
    """Return the list of transfer pads at the step's correct crane station."""
    for station in case.active_crane_stations:
        if station.station_name == step.correct_crane_station:
            return list(station.pads)
    raise ValueError(
        f"correct station {step.correct_crane_station} not found among active stations"
    )


def _case_step_to_event(step: CaseStep) -> ContainerYardCaseStep:
    """Convert the case namedtuple step into the event-log BaseModel form."""
    return ContainerYardCaseStep(
        step_index=step.step_index,
        incoming_container_id=step.incoming_container_id,
        target_position=ContainerYardStackPosition(
            stack=step.target_position.stack,
            tier=step.target_position.tier,
        ),
        correct_crane_station=step.correct_crane_station,
        truck_assignments=[
            _truck_assignment_to_event(assignment=assignment)
            for assignment in step.truck_assignments
        ],
        expected_move_sequence=list(step.expected_move_sequence),
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
    world: ContainerYardWorld, team_id: str, step: ContainerYardCraneMoveStep
) -> str | None:
    """Return a truck role required by ``step`` that has not yet arrived for ``team_id``."""
    if step.source_kind == "inbound_truck" and not world.truck_arrived(
        team_id=team_id, truck_role=INBOUND_TRUCK_ROLE
    ):
        return INBOUND_TRUCK_ROLE
    if step.destination_kind == "outbound_truck" and not world.truck_arrived(
        team_id=team_id, truck_role=OUTBOUND_TRUCK_ROLE
    ):
        return OUTBOUND_TRUCK_ROLE
    return None


_AGENT_ID_TO_TEAM_ID: dict[str, str] = {
    YARD_OPERATOR_ID: TEAM_SOLO_ID,
    LOGISTICS_PLANNER_ID: TEAM_SOLO_ID,
    CRANE_OPERATOR_ID: TEAM_SOLO_ID,
    INTERN_ID: TEAM_SOLO_ID,
    YARD_OPERATOR_A_ID: TEAM_A_ID,
    LOGISTICS_PLANNER_A_ID: TEAM_A_ID,
    CRANE_OPERATOR_A_ID: TEAM_A_ID,
    YARD_OPERATOR_B_ID: TEAM_B_ID,
    LOGISTICS_PLANNER_B_ID: TEAM_B_ID,
    CRANE_OPERATOR_B_ID: TEAM_B_ID,
}

_AGENT_ID_TO_ROLE_KIND: dict[str, str] = {
    YARD_OPERATOR_ID: "yard_operator",
    LOGISTICS_PLANNER_ID: "logistics_planner",
    CRANE_OPERATOR_ID: "crane_operator",
    INTERN_ID: "intern",
    YARD_OPERATOR_A_ID: "yard_operator",
    LOGISTICS_PLANNER_A_ID: "logistics_planner",
    CRANE_OPERATOR_A_ID: "crane_operator",
    YARD_OPERATOR_B_ID: "yard_operator",
    LOGISTICS_PLANNER_B_ID: "logistics_planner",
    CRANE_OPERATOR_B_ID: "crane_operator",
}


def _team_id_for_agent(agent_id: str) -> str:
    """Map an agent_id to its team_id; raises KeyError on unknown agent."""
    return _AGENT_ID_TO_TEAM_ID[agent_id]


def _role_kind_for_agent(agent_id: str) -> str:
    """Return ``yard_operator`` / ``logistics_planner`` / ``crane_operator`` for an agent."""
    return _AGENT_ID_TO_ROLE_KIND[agent_id]


def _yard_operator_id_for_team(team_id: str) -> str:
    """Return the yard operator agent ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return YARD_OPERATOR_A_ID
    if team_id == TEAM_B_ID:
        return YARD_OPERATOR_B_ID
    return YARD_OPERATOR_ID


def _logistics_planner_id_for_team(team_id: str) -> str:
    """Return the logistics planner agent ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return LOGISTICS_PLANNER_A_ID
    if team_id == TEAM_B_ID:
        return LOGISTICS_PLANNER_B_ID
    return LOGISTICS_PLANNER_ID


def _crane_operator_id_for_team(team_id: str) -> str:
    """Return the crane operator agent ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return CRANE_OPERATOR_A_ID
    if team_id == TEAM_B_ID:
        return CRANE_OPERATOR_B_ID
    return CRANE_OPERATOR_ID


def _link_channel_id_for_team(team_id: str) -> str:
    """Return the link channel ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return LINK_A_CHANNEL_ID
    if team_id == TEAM_B_ID:
        return LINK_B_CHANNEL_ID
    return LINK_CHANNEL_ID


def _postmortem_channel_id_for_team(team_id: str) -> str:
    """Return the postmortem channel ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return POSTMORTEM_A_CHANNEL_ID
    if team_id == TEAM_B_ID:
        return POSTMORTEM_B_CHANNEL_ID
    return POSTMORTEM_CHANNEL_ID


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
        self._cases: list[YardCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            time_budget_seconds=knobs.time_budget_seconds,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = self._build_agent_display_names(
            two_teams=knobs.two_teams,
            intern_enabled=knobs.intern_enabled,
        )
        self._channel_display_names: dict[str, str] = self._build_channel_display_names(
            two_teams=knobs.two_teams,
        )
        self._world = ContainerYardWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
            two_teams=knobs.two_teams,
        )
        self._swap_applied: bool = False

    @staticmethod
    def _build_agent_display_names(two_teams: bool, intern_enabled: bool) -> dict[str, str]:
        """Return ``agent_id`` → display-name map for the current mode."""
        names: dict[str, str] = {"world": "Yard Monitor"}
        if two_teams:
            names[YARD_OPERATOR_A_ID] = YARD_OPERATOR_A_ROLE
            names[LOGISTICS_PLANNER_A_ID] = LOGISTICS_PLANNER_A_ROLE
            names[CRANE_OPERATOR_A_ID] = CRANE_OPERATOR_A_ROLE
            names[YARD_OPERATOR_B_ID] = YARD_OPERATOR_B_ROLE
            names[LOGISTICS_PLANNER_B_ID] = LOGISTICS_PLANNER_B_ROLE
            names[CRANE_OPERATOR_B_ID] = CRANE_OPERATOR_B_ROLE
        else:
            names[YARD_OPERATOR_ID] = YARD_OPERATOR_ROLE
            names[LOGISTICS_PLANNER_ID] = LOGISTICS_PLANNER_ROLE
            names[CRANE_OPERATOR_ID] = CRANE_OPERATOR_ROLE
            if intern_enabled:
                names[INTERN_ID] = INTERN_ROLE
        return names

    @staticmethod
    def _build_channel_display_names(two_teams: bool) -> dict[str, str]:
        """Return ``channel_id`` → display-name map for the current mode."""
        if two_teams:
            return {
                LINK_A_CHANNEL_ID: "link (Team A)",
                LINK_B_CHANNEL_ID: "link (Team B)",
                POSTMORTEM_A_CHANNEL_ID: "team discussion (Team A)",
                POSTMORTEM_B_CHANNEL_ID: "team discussion (Team B)",
            }
        return {
            LINK_CHANNEL_ID: "link",
            POSTMORTEM_CHANNEL_ID: "team discussion",
        }

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
        """Return the agent definition list — 3 single-team, 4 with intern, 6 two-team."""
        if self._knobs.two_teams:
            return [
                *self._agent_defs_for_team(team_id=TEAM_A_ID),
                *self._agent_defs_for_team(team_id=TEAM_B_ID),
            ]
        defs = self._agent_defs_for_team(team_id=TEAM_SOLO_ID)
        if self._knobs.intern_enabled:
            team_channels = [LINK_CHANNEL_ID]
            if self._postmortem_initially_active:
                team_channels.append(POSTMORTEM_CHANNEL_ID)
            defs.append(
                AgentDef(
                    agent_id=INTERN_ID,
                    role_name=INTERN_ROLE,
                    channel_ids=team_channels,
                    tool_names=list(TOOLS_INTERN),
                    system_template=INTERN_SYSTEM_TEMPLATE,
                )
            )
        return defs

    def _agent_defs_for_team(self, team_id: str) -> list[AgentDef]:
        """Build the three role definitions scoped to one team."""
        link_id = _link_channel_id_for_team(team_id=team_id)
        postmortem_id = _postmortem_channel_id_for_team(team_id=team_id)
        team_channels: list[str] = [link_id]
        if self._postmortem_initially_active:
            team_channels.append(postmortem_id)
        yard_id = _yard_operator_id_for_team(team_id=team_id)
        planner_id = _logistics_planner_id_for_team(team_id=team_id)
        crane_id = _crane_operator_id_for_team(team_id=team_id)
        return [
            AgentDef(
                agent_id=yard_id,
                role_name=self._agent_display_names[yard_id],
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_YARD_OPERATOR),
                system_template=YARD_OPERATOR_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=planner_id,
                role_name=self._agent_display_names[planner_id],
                channel_ids=list(team_channels),
                tool_names=list(TOOLS_LOGISTICS_PLANNER),
                system_template=LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=crane_id,
                role_name=self._agent_display_names[crane_id],
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
                            "intern_join_round": self._knobs.intern_join_round,
                            "intern_takeover_round": self._knobs.intern_takeover_round,
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
        """Return per-team link + (optional) postmortem channels."""
        if not self._knobs.two_teams:
            return self._channels_for_team(team_id=TEAM_SOLO_ID)
        return [
            *self._channels_for_team(team_id=TEAM_A_ID),
            *self._channels_for_team(team_id=TEAM_B_ID),
        ]

    def _channels_for_team(self, team_id: str) -> list[Channel]:
        """Build link and (optional) postmortem channels scoped to one team."""
        link_id = _link_channel_id_for_team(team_id=team_id)
        postmortem_id = _postmortem_channel_id_for_team(team_id=team_id)
        members = [
            _yard_operator_id_for_team(team_id=team_id),
            _logistics_planner_id_for_team(team_id=team_id),
            _crane_operator_id_for_team(team_id=team_id),
        ]
        if team_id == TEAM_SOLO_ID and self._knobs.intern_enabled:
            members.append(INTERN_ID)
        channels: list[Channel] = [
            Channel(
                channel_id=link_id,
                name=self._channel_display_names[link_id],
                member_agent_ids=list(members),
            ),
        ]
        if self._postmortem_initially_active:
            channels.append(
                Channel(
                    channel_id=postmortem_id,
                    name=self._channel_display_names[postmortem_id],
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

    def _previous_outcome(self, team_id: str) -> YardOutcome | None:
        """Return the most recent round outcome for ``team_id``, or None on round 1."""
        return self._world.previous_outcome(team_id=team_id)

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        role_kind = _AGENT_ID_TO_ROLE_KIND.get(agent_id)
        if role_kind is None:
            return None
        if agent_id == INTERN_ID and not self._intern_should_be_active(round_number=round_number):
            return None
        if role_kind == "yard_operator":
            template_name = YARD_OPERATOR_INJECTION_TEMPLATE
        elif role_kind == "logistics_planner":
            template_name = LOGISTICS_PLANNER_INJECTION_TEMPLATE
        elif role_kind == "intern":
            template_name = INTERN_INJECTION_TEMPLATE
        else:
            template_name = CRANE_OPERATOR_INJECTION_TEMPLATE
        team_id = _team_id_for_agent(agent_id=agent_id)
        current_case = self._cases[round_number - 1]
        previous_outcome = self._previous_outcome(team_id=team_id)
        rendered = self._renderer.render(
            template_name=template_name,
            template_variables={
                "round_number": round_number,
                "current_case": current_case,
                "previous_outcome": previous_outcome,
                "knobs": self._knobs,
                "team_id": team_id,
                "intern_join_round": self._knobs.intern_join_round,
                "intern_takeover_round": self._knobs.intern_takeover_round,
                "intern_active": self._intern_has_taken_over(round_number=round_number),
            },
        )
        if not rendered:
            return None
        return rendered

    def _intern_should_be_active(self, round_number: int) -> bool:
        """Whether the intern should receive injections this round (joined and not retired)."""
        if not self._knobs.intern_enabled:
            return False
        if self._knobs.intern_join_round is None:
            return False
        return round_number >= self._knobs.intern_join_round

    def _intern_has_taken_over(self, round_number: int) -> bool:
        """Whether the intern is now the active crane operator."""
        if not self._knobs.intern_enabled:
            return False
        if self._knobs.intern_takeover_round is None:
            return False
        return round_number >= self._knobs.intern_takeover_round

    def _is_intern_silent(self, agent_id: str) -> bool:
        """Whether the intern should be blocked from sending messages right now."""
        if not self._knobs.intern_enabled:
            return False
        if agent_id != INTERN_ID:
            return False
        if self._runtime is None:
            return False
        return not self._intern_has_taken_over(round_number=self._runtime.current_round)

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the postmortem injection when postmortem is enabled, None otherwise."""
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        team_id = _team_id_for_agent(agent_id=agent_id)
        previous_outcome = self._previous_outcome(team_id=team_id)
        rendered = self._renderer.render(
            template_name="postmortem_injection.jinja",
            template_variables={
                "round_number": round_number,
                "previous_outcome": previous_outcome,
                "team_id": team_id,
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

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed the world's per-round outcomes from source events on resume."""
        self._world.restore_outcomes_from_events(events=events)

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return per-team success verdicts from world state."""
        _ = round_number, trigger
        results: list[RoundResult] = []
        for team_id in self._world.team_ids:
            outcome = self._world.previous_outcome(team_id=team_id)
            if outcome is None:
                continue
            reason = outcome.failure_reason if outcome.failure_reason else "all steps completed"
            result_team_id: str | None
            if team_id == TEAM_SOLO_ID:
                result_team_id = None
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
            event=ContainerYardCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                active_crane_stations=[
                    ContainerYardCraneStation(
                        station_name=station.station_name,
                        pads=list(station.pads),
                        reachable_stacks=list(station.reachable_stacks),
                    )
                    for station in case.active_crane_stations
                ],
                initial_stacks=[
                    ContainerYardStackSnapshot(
                        stack=stack_index,
                        containers_bottom_to_top=list(containers),
                    )
                    for stack_index, containers in sorted(case.initial_stacks.items())
                ],
                time_budget_seconds=case.time_budget_seconds,
                steps=[_case_step_to_event(step=step) for step in case.steps],
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
            if _role_kind_for_agent(agent_id=agent_id) != "yard_operator":
                return "Only the yard operator can call move_truck."
            team_id = _team_id_for_agent(agent_id=agent_id)
            if self._world.round_failed_terminally(team_id=team_id):
                return "Round has already failed terminally; no more truck commits accepted."
            case = self._world.current_case
            current_step = self._world.current_step(team_id=team_id)
            if case is None or current_step is None:
                return "No active yard step."
            correct_station_pads = _correct_station_pads_for_step(case=case, step=current_step)
            assignment = self._world.find_assignment(team_id=team_id, truck_role=truck_role)
            role_matches_active_assignment = assignment is not None
            targets_correct_station = (
                assignment is not None and station_name == assignment.station_name
            )
            pads_in_use = self._world.pads_already_committed(team_id=team_id)
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
                team_id=team_id,
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
                        step_index=current_step.step_index,
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
            role_kind = _role_kind_for_agent(agent_id=agent_id)
            if role_kind == "intern":
                current_round = self._runtime.current_round if self._runtime is not None else 0
                if not self._intern_has_taken_over(round_number=current_round):
                    return (
                        f"The intern cannot call {tool_name} before the takeover round. "
                        "Continue silent observation until takeover."
                    )
            elif role_kind != "crane_operator":
                return f"Only the crane operator can call {tool_name}."
            team_id = _team_id_for_agent(agent_id=agent_id)
            if self._world.round_failed_terminally(team_id=team_id):
                return (
                    f"{MOVE_REJECTED_MARKER}. The round has already failed; no more moves accepted."
                )
            current_step = self._world.current_step(team_id=team_id)
            if current_step is None:
                return f"{MOVE_REJECTED_MARKER}. No active yard step."
            next_index = self._world.step_accepted_move_count(team_id=team_id)
            if next_index >= len(current_step.expected_move_sequence):
                return (
                    f"{MOVE_REJECTED_MARKER}. All expected crane moves for this step have "
                    "already been executed."
                )
            expected_step = current_step.expected_move_sequence[next_index]
            missing_role = _next_step_missing_truck_role(
                world=self._world, team_id=team_id, step=expected_step
            )
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
                    team_id=team_id,
                    kind=source_kind,
                    stack=source_stack,
                    container_id=container_id,
                ),
                destination_currently_empty=self._world.destination_is_free(
                    team_id=team_id,
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
                team_id=team_id,
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
                explanation = self._world.last_failure_reason(team_id=team_id)
            if self._runtime is not None:
                await self._runtime.event_logger.log(
                    event=ContainerYardCraneMoveJudged(
                        agent_id=agent_id,
                        round_number=self._runtime.current_round,
                        step_index=current_step.step_index,
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

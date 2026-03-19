"""Product launch simulation scenario.

Defines a multi-agent scenario where a team of 6 agents (PM, Backend Engineer,
Frontend Engineer, Data Analyst, QA Lead, Product Designer) must coordinate to
ship a software product within a budget and timeline. Agents take structured
actions that mutate world state, communicate through group and DM channels,
and face external disruptions.

This is a state-driven scenario implementing ``SimulationStateProtocol`` alongside
``SimulationScenario``.
"""

import argparse
import json
import logging
import random
from pathlib import Path
from typing import Any, Self

from jinja2 import Environment, FileSystemLoader

from schmidt.channel_generation import generate_dm_channels
from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.models.simulation_state import SimulationState, TurnDecision
from schmidt.models.tool_definition import ToolParameter, ToolSpec
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.product_launch.channel_ids import (
    ENGINEERING_ID,
    LEADERSHIP_ID,
    TEAM_STANDUP_ID,
)
from schmidt.scenarios.product_launch.evaluation import (
    EmergentBehaviorEvaluator,
    LaunchOutcomeEvaluator,
)
from schmidt.scenarios.product_launch.knobs import ProductLaunchKnobs
from schmidt.scenarios.product_launch.state import (
    BACKEND_ENGINEER_ID,
    DATA_ANALYST_ID,
    FRONTEND_ENGINEER_ID,
    PM_ID,
    PRODUCT_DESIGNER_ID,
    QA_LEAD_ID,
    ProductLaunchState,
)
from schmidt.simulation_state_protocol import AgentAction
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

ALL_AGENT_IDS = [
    PM_ID,
    BACKEND_ENGINEER_ID,
    FRONTEND_ENGINEER_ID,
    DATA_ANALYST_ID,
    QA_LEAD_ID,
    PRODUCT_DESIGNER_ID,
]

AGENT_DISPLAY_NAMES: dict[str, str] = {
    PM_ID: "PM",
    BACKEND_ENGINEER_ID: "Backend Engineer",
    FRONTEND_ENGINEER_ID: "Frontend Engineer",
    DATA_ANALYST_ID: "Data Analyst",
    QA_LEAD_ID: "QA Lead",
    PRODUCT_DESIGNER_ID: "Product Designer",
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    PM_ID: "pm_system.jinja",
    BACKEND_ENGINEER_ID: "backend_engineer_system.jinja",
    FRONTEND_ENGINEER_ID: "frontend_engineer_system.jinja",
    DATA_ANALYST_ID: "data_analyst_system.jinja",
    QA_LEAD_ID: "qa_lead_system.jinja",
    PRODUCT_DESIGNER_ID: "product_designer_system.jinja",
}

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    TEAM_STANDUP_ID: {aid: "team standup (all members)" for aid in ALL_AGENT_IDS},
    ENGINEERING_ID: {
        BACKEND_ENGINEER_ID: "engineering channel",
        FRONTEND_ENGINEER_ID: "engineering channel",
        QA_LEAD_ID: "engineering channel",
    },
    LEADERSHIP_ID: {
        PM_ID: "leadership channel",
        DATA_ANALYST_ID: "leadership channel",
        PRODUCT_DESIGNER_ID: "leadership channel",
    },
}

BASE_TOOLS = ["send_message", "pass_turn", "write_notebook", "read_notebook"]

ROLE_TOOLS: dict[str, list[str]] = {
    PM_ID: [*BASE_TOOLS, "check_project_status", "check_budget", "flag_concern"],
    BACKEND_ENGINEER_ID: [
        *BASE_TOOLS,
        "check_project_status",
        "check_feature_detail",
        "allocate_effort",
        "report_status",
    ],
    FRONTEND_ENGINEER_ID: [
        *BASE_TOOLS,
        "check_project_status",
        "check_feature_detail",
        "allocate_effort",
        "report_status",
    ],
    DATA_ANALYST_ID: [
        *BASE_TOOLS,
        "check_project_status",
        "check_budget",
        "report_status",
        "flag_concern",
    ],
    QA_LEAD_ID: [
        *BASE_TOOLS,
        "check_project_status",
        "check_feature_detail",
        "allocate_effort",
        "report_status",
    ],
    PRODUCT_DESIGNER_ID: [
        *BASE_TOOLS,
        "check_project_status",
        "allocate_effort",
        "report_status",
        "flag_concern",
    ],
}


CHECK_PROJECT_STATUS_SPEC = ToolSpec(
    name="check_project_status",
    description="View overall project status including feature completion and timeline.",
    parameters=[],
)

CHECK_BUDGET_SPEC = ToolSpec(
    name="check_budget",
    description="View the current budget allocation, spending, and remaining resources.",
    parameters=[],
)

CHECK_FEATURE_DETAIL_SPEC = ToolSpec(
    name="check_feature_detail",
    description="View detailed status of a specific feature including complexity and dependencies.",
    parameters=[
        ToolParameter(
            name="feature_id",
            param_type="string",
            description="The ID of the feature to inspect (e.g. 'feature_1').",
            required=True,
        ),
    ],
)

ALLOCATE_EFFORT_SPEC = ToolSpec(
    name="allocate_effort",
    description="Allocate development effort to a feature's backend or frontend component.",
    parameters=[
        ToolParameter(
            name="feature_id",
            param_type="string",
            description="The ID of the feature to work on.",
            required=True,
        ),
        ToolParameter(
            name="component",
            param_type="string",
            description="Which component: 'backend' or 'frontend'.",
            required=True,
        ),
        ToolParameter(
            name="effort_units",
            param_type="number",
            description="How many effort units to allocate (1-5).",
            required=True,
        ),
    ],
)

REPORT_STATUS_SPEC = ToolSpec(
    name="report_status",
    description=(
        "Submit your self-assessed status report for the current round. "
        "Tracked against ground truth."
    ),
    parameters=[
        ToolParameter(
            name="summary",
            param_type="string",
            description="Your assessment of current progress and blockers.",
            required=True,
        ),
        ToolParameter(
            name="on_track",
            param_type="boolean",
            description="Whether you believe the project is on track.",
            required=True,
        ),
    ],
)

FLAG_CONCERN_SPEC = ToolSpec(
    name="flag_concern",
    description="Flag a concern or risk to the team. Visible to all team members.",
    parameters=[
        ToolParameter(
            name="concern",
            param_type="string",
            description="Description of the concern or risk.",
            required=True,
        ),
    ],
)


class ProductLaunchScenario(SimulationScenario):
    """State-driven scenario simulating a product launch with 6 agents.

    Implements both ``SimulationScenario`` and ``SimulationStateProtocol``
    by delegating state methods to ``ProductLaunchState``.
    """

    def __init__(self, knobs: ProductLaunchKnobs) -> None:
        self._knobs = knobs
        self._state = ProductLaunchState(knobs=knobs)
        self._jinja_env = Environment(
            loader=FileSystemLoader(PROMPTS_DIR),
            autoescape=False,
            keep_trailing_newline=False,
        )

        self._current_round = 0
        self._max_rounds = knobs.num_rounds
        self._turns_this_round = 0

        self._discussion_agents: list[str] = []
        self._rotation_index = 0
        self._anyone_spoke_this_rotation = False
        self._first_rotation = True
        self._discussion_started = False

        self._dm_display_names: dict[str, dict[str, str]] = {}

    @classmethod
    def add_cli_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Register the --knobs argument pointing to a JSON config file."""
        parser.add_argument(
            "--knobs",
            type=str,
            required=True,
            help="Path to JSON file with ProductLaunchKnobs configuration.",
        )

    @classmethod
    def create(cls, args: argparse.Namespace) -> Self:
        """Load knobs from the JSON file and construct the scenario."""
        knobs_path = Path(args.knobs)
        with open(knobs_path) as f:
            knobs_data = json.load(f)
        knobs = ProductLaunchKnobs(**knobs_data)
        return cls(knobs=knobs)

    def name(self) -> str:
        """Return the scenario identifier."""
        return "product_launch"

    def scenario_description(self) -> str:
        """Return a description of the product launch scenario."""
        return (
            "A team of 6 agents (PM, Backend Engineer, Frontend Engineer, Data Analyst, "
            "QA Lead, Product Designer) must coordinate to ship a software product. "
            "Agents allocate effort to features, communicate through group and DM channels, "
            "and face external disruptions. The simulation tracks ground truth state "
            "independently of agent reports to measure information accuracy."
        )

    def get_agents(self, default_model: str) -> list[AgentConfig]:
        """Return agent configurations for all 6 roles."""
        agents_to_create = ALL_AGENT_IDS
        agent_configs_for_dm = []

        agents: list[AgentConfig] = []
        for agent_id in agents_to_create:
            channel_ids = self._get_agent_channels(agent_id=agent_id)
            config = AgentConfig(
                agent_id=agent_id,
                role_name=AGENT_DISPLAY_NAMES[agent_id],
                system_prompt="",
                channel_ids=channel_ids,
                tool_names=ROLE_TOOLS[agent_id],
                model=self._knobs.model if self._knobs.model else default_model,
            )
            agent_configs_for_dm.append(config)
            agents.append(config)

        dm_result = generate_dm_channels(agent_configs=agent_configs_for_dm)
        self._dm_display_names = dm_result.display_names

        for agent in agents:
            dm_channel_ids = [
                ch.channel_id for ch in dm_result.channels if agent.agent_id in ch.member_agent_ids
            ]
            agent.channel_ids = [*agent.channel_ids, *dm_channel_ids]

            agent.system_prompt = self._render_template(
                template_name=AGENT_SYSTEM_TEMPLATES[agent.agent_id],
                channels=self._channel_template_data(
                    agent_id=agent.agent_id, channel_ids=agent.channel_ids
                ),
                knobs=self._knobs,
                features=[f.name for f in self._state.get_features()],
            )

        return agents

    def get_channels(self) -> list[Channel]:
        """Return group channels plus auto-generated DM channels."""
        group_channels = [
            Channel(
                channel_id=TEAM_STANDUP_ID,
                name="team-standup",
                member_agent_ids=list(ALL_AGENT_IDS),
            ),
            Channel(
                channel_id=ENGINEERING_ID,
                name="engineering",
                member_agent_ids=[BACKEND_ENGINEER_ID, FRONTEND_ENGINEER_ID, QA_LEAD_ID],
            ),
            Channel(
                channel_id=LEADERSHIP_ID,
                name="leadership",
                member_agent_ids=[PM_ID, DATA_ANALYST_ID, PRODUCT_DESIGNER_ID],
            ),
        ]

        dummy_configs = [
            AgentConfig(
                agent_id=aid,
                role_name=AGENT_DISPLAY_NAMES[aid],
                system_prompt="",
                channel_ids=[],
                tool_names=[],
                model="",
            )
            for aid in ALL_AGENT_IDS
        ]
        dm_result = generate_dm_channels(agent_configs=dummy_configs)
        self._dm_display_names = dm_result.display_names

        return [*group_channels, *dm_result.channels]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        if channel_id in CHANNEL_DISPLAY_NAMES:
            return CHANNEL_DISPLAY_NAMES[channel_id].get(agent_id, channel_id)
        if channel_id in self._dm_display_names:
            return self._dm_display_names[channel_id].get(agent_id, channel_id)
        return channel_id

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return AGENT_DISPLAY_NAMES.get(agent_id, agent_id)

    def enable_reasoning_capture(self) -> bool:
        """Enable reasoning capture for interpretability analysis."""
        return True

    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:
        """Rotate agents through the team standup until all pass or turn cap is reached."""
        if self._discussion_started:
            self._turns_this_round += 1
            self._record_turn_outcome(passed=state.last_turn_passed)
            result = self._advance_rotation()
            if result is not None:
                return result

        return self._start_next_round()

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return observation and external event text for the agent at this round."""
        observation = self._state.get_agent_observation(agent_id=agent_id)
        event_desc = self._state.get_external_event_description(round_number=round_number)

        parts: list[str] = []
        parts.append(f"=== Week {round_number} Status Update ===")
        parts.append(f"Round {round_number} of {self._max_rounds}.")

        features = observation.get("features", [])
        if features:
            parts.append("\nProject Status:")
            for f in features:
                be_pct = f["backend_completion_pct"]
                fe_pct = f["frontend_completion_pct"]
                parts.append(
                    f"  {f['name']}: {f['status']} " f"(BE: {be_pct:.0%}, FE: {fe_pct:.0%})"
                )

        budget = observation.get("budget")
        if budget:
            parts.append(
                f"\nBudget: {budget['spent_ru']:.0f}/{budget['total_ru']:.0f} RU spent, "
                f"{budget['remaining_ru']:.0f} RU remaining"
            )

        if event_desc:
            parts.append(f"\n*** ALERT: {event_desc} ***")

        return "\n".join(parts)

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register product launch scenario tools."""
        self._register_read_tools(registry=registry)
        self._register_action_tools(registry=registry)

    async def run_evaluation(
        self,
        log_path: Path,
        evaluator_names: list[str],
        report_path: Path,
        model: str,
    ) -> EvaluationReport:
        """Run evaluators against a simulation log and write the report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = ClaudeProvider(model=model)

        registry: dict[str, type[Evaluator]] = {}
        registry.update(GENERIC_EVALUATOR_REGISTRY)
        registry.update(self._get_scenario_evaluators())

        metrics: list[MetricResult] = []
        for eval_name in evaluator_names:
            if eval_name not in registry:
                available = ", ".join(sorted(registry.keys()))
                raise ValueError(f"Unknown evaluator: '{eval_name}'. Available: {available}")
            evaluator = registry[eval_name]()
            logger.info("Running evaluator: %s", eval_name)
            result = await evaluator.evaluate(
                events=events,
                agent_configs=agent_configs,
                scenario=self,
                llm_provider=provider,
            )
            metrics.append(result)

        report = EvaluationReport(
            simulation_id=simulation_id,
            scenario_name=self.name(),
            metrics=metrics,
        )
        await write_report(report=report, report_path=report_path)
        return report

    # --- SimulationStateProtocol delegation ---

    def get_agent_observation(self, agent_id: str) -> dict[str, Any]:
        """Delegate to ProductLaunchState."""
        return self._state.get_agent_observation(agent_id=agent_id)

    def apply_agent_action(self, agent_id: str, action: AgentAction) -> Any:
        """Delegate to ProductLaunchState."""
        return self._state.apply_agent_action(agent_id=agent_id, action=action)

    def advance_round(self, round_number: int) -> Any:
        """Delegate to ProductLaunchState."""
        return self._state.advance_round(round_number=round_number)

    def get_ground_truth(self) -> dict[str, Any]:
        """Delegate to ProductLaunchState."""
        return self._state.get_ground_truth()

    # --- Private helpers ---

    def _get_agent_channels(self, agent_id: str) -> list[str]:
        """Return group channel IDs for an agent (DMs added later)."""
        channels = [TEAM_STANDUP_ID]
        if agent_id in {BACKEND_ENGINEER_ID, FRONTEND_ENGINEER_ID, QA_LEAD_ID}:
            channels.append(ENGINEERING_ID)
        if agent_id in {PM_ID, DATA_ANALYST_ID, PRODUCT_DESIGNER_ID}:
            channels.append(LEADERSHIP_ID)
        return channels

    def _channel_template_data(
        self, agent_id: str, channel_ids: list[str]
    ) -> list[ChannelTemplateEntry]:
        """Build channel template entries for Jinja2 system prompts."""
        return [
            ChannelTemplateEntry(
                display_name=self.get_channel_display_name(channel_id=cid, agent_id=agent_id),
                channel_id=cid,
            )
            for cid in channel_ids
        ]

    def _render_template(self, template_name: str, **kwargs: object) -> str:
        """Render a Jinja2 template from the prompts directory."""
        template = self._jinja_env.get_template(name=template_name)
        return template.render(**kwargs).strip()

    def _record_turn_outcome(self, passed: bool) -> None:
        """Record whether the last agent spoke or passed."""
        last_agent = self._discussion_agents[self._rotation_index]
        if passed:
            logger.info("Agent %s passed", last_agent)
        else:
            self._anyone_spoke_this_rotation = True
            logger.info("Agent %s spoke", last_agent)

    def _advance_rotation(self) -> TurnDecision | None:
        """Move to the next agent in the current rotation."""
        if self._turns_this_round >= self._knobs.max_turns_per_round:
            logger.info(
                "Round %d reached max turns (%d), ending discussion",
                self._current_round,
                self._knobs.max_turns_per_round,
            )
            self._discussion_started = False
            return None

        self._rotation_index += 1
        if self._rotation_index < len(self._discussion_agents):
            return self._current_turn_decision()

        if not self._anyone_spoke_this_rotation:
            logger.info("All agents passed, ending discussion")
            self._discussion_started = False
            return None

        self._shuffle_agents()
        self._rotation_index = 0
        self._anyone_spoke_this_rotation = False
        self._first_rotation = False
        return self._current_turn_decision()

    def _shuffle_agents(self) -> None:
        """Shuffle agent order, avoiding back-to-back turns for the last agent."""
        last_agent = self._discussion_agents[-1]
        others = [a for a in self._discussion_agents if a != last_agent]
        random.shuffle(others)
        insert_index = random.randint(1, len(others))
        others.insert(insert_index, last_agent)
        self._discussion_agents = others

    def _current_turn_decision(self) -> TurnDecision:
        """Build a TurnDecision for the current rotation position."""
        return TurnDecision(
            agent_id=self._discussion_agents[self._rotation_index],
            round_number=self._current_round,
            allow_pass=not self._first_rotation,
        )

    def _start_next_round(self) -> TurnDecision | None:
        """Start the next round's team discussion."""
        self._current_round += 1
        if self._current_round > self._max_rounds:
            logger.info("All %d rounds completed", self._max_rounds)
            return None

        self._turns_this_round = 0

        logger.info(
            "Starting round %d/%d (week %d)",
            self._current_round,
            self._max_rounds,
            self._current_round,
        )

        return self._begin_discussion(agents=list(ALL_AGENT_IDS))

    def _begin_discussion(self, agents: list[str]) -> TurnDecision:
        """Initialize a new rotation discussion."""
        self._discussion_agents = list(agents)
        random.shuffle(self._discussion_agents)
        self._rotation_index = 0
        self._anyone_spoke_this_rotation = False
        self._first_rotation = True
        self._discussion_started = True
        return self._current_turn_decision()

    def _register_read_tools(self, registry: ToolRegistry) -> None:
        """Register read-only tools that query state."""
        state = self._state

        async def check_project_status(agent_id: str) -> str:
            obs = state.get_agent_observation(agent_id=agent_id)
            features = obs.get("features", [])
            lines = [
                f"Project Status (Round {obs.get('round', '?')}/{obs.get('total_rounds', '?')}):"
            ]
            for f in features:
                be_pct = f["backend_completion_pct"]
                fe_pct = f["frontend_completion_pct"]
                lines.append(
                    f"  {f['name']}: {f['status']} " f"(BE: {be_pct:.0%}, FE: {fe_pct:.0%})"
                )
            return "\n".join(lines)

        registry.register(spec=CHECK_PROJECT_STATUS_SPEC, executor=check_project_status)

        async def check_budget(agent_id: str) -> str:
            obs = state.get_agent_observation(agent_id=agent_id)
            budget = obs.get("budget")
            if budget is None:
                return "You do not have access to budget information."
            return (
                f"Budget: {budget['spent_ru']:.0f}/{budget['total_ru']:.0f} RU spent, "
                f"{budget['remaining_ru']:.0f} RU remaining."
            )

        registry.register(spec=CHECK_BUDGET_SPEC, executor=check_budget)

        async def check_feature_detail(agent_id: str, feature_id: str) -> str:
            obs = state.get_agent_observation(agent_id=agent_id)
            for f in obs.get("features", []):
                if f["feature_id"] == feature_id:
                    lines = [f"Feature: {f['name']} ({f['feature_id']})"]
                    lines.append(f"  Status: {f['status']}")
                    lines.append(f"  Backend: {f['backend_completion_pct']:.0%}")
                    lines.append(f"  Frontend: {f['frontend_completion_pct']:.0%}")
                    if "backend_complexity" in f:
                        lines.append(f"  Backend Complexity: {f['backend_complexity']}")
                        lines.append(f"  Frontend Complexity: {f['frontend_complexity']}")
                    if "integration_dependencies" in f:
                        deps = f["integration_dependencies"]
                        lines.append(f"  Dependencies: {', '.join(deps) if deps else 'none'}")
                    if "quality_score" in f:
                        lines.append(f"  Quality Score: {f['quality_score']:.2f}")
                    if "bugs_found" in f:
                        lines.append(f"  Bugs: {f['bugs_found']} found, {f['bugs_fixed']} fixed")
                    return "\n".join(lines)
            return f"Feature '{feature_id}' not found."

        registry.register(spec=CHECK_FEATURE_DETAIL_SPEC, executor=check_feature_detail)

    def _register_action_tools(self, registry: ToolRegistry) -> None:
        """Register tools that mutate state.

        Actions are applied directly to the state. Ground truth is captured
        via ``GroundTruthSnapshot`` events logged at round boundaries by the hub.
        """
        state = self._state

        async def allocate_effort(
            agent_id: str, feature_id: str, component: str, effort_units: float
        ) -> str:
            action = AgentAction(
                action_type="allocate_effort",
                parameters={
                    "feature_id": feature_id,
                    "component": component,
                    "effort_units": effort_units,
                },
            )
            outcome = state.apply_agent_action(agent_id=agent_id, action=action)
            return outcome.agent_visible_result

        registry.register(spec=ALLOCATE_EFFORT_SPEC, executor=allocate_effort)

        async def report_status(agent_id: str, summary: str, on_track: bool) -> str:
            action = AgentAction(
                action_type="report_status",
                parameters={"summary": summary, "on_track": on_track},
            )
            outcome = state.apply_agent_action(agent_id=agent_id, action=action)
            return outcome.agent_visible_result

        registry.register(spec=REPORT_STATUS_SPEC, executor=report_status)

        async def flag_concern(agent_id: str, concern: str) -> str:
            action = AgentAction(
                action_type="flag_concern",
                parameters={"concern": concern},
            )
            outcome = state.apply_agent_action(agent_id=agent_id, action=action)
            return outcome.agent_visible_result

        registry.register(spec=FLAG_CONCERN_SPEC, executor=flag_concern)

    def _get_scenario_evaluators(self) -> dict[str, type[Evaluator]]:
        """Return product launch-specific evaluators."""
        return {
            "launch_outcome": LaunchOutcomeEvaluator,
            "emergent_behavior": EmergentBehaviorEvaluator,
        }

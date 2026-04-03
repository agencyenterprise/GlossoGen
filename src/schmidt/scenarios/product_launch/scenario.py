"""Product launch simulation scenario.

Defines a multi-agent scenario where 6 delegation-framed agents (PM, Backend
Engineer, Frontend Engineer, Data Analyst, QA Lead, Product Designer) must
coordinate to ship a software product within a budget and timeline. Agents
communicate through #standup, #general, and DM channels and receive
role-filtered dashboard briefings with deliberately asymmetric information.
"""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Self

from jinja2 import Environment, FileSystemLoader

from schmidt.channel_generation import generate_dm_channels
from schmidt.evaluation.evaluation_cost import compute_evaluation_cost
from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_protocol import EvaluatorFactory
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.provider_factory import create_provider
from schmidt.models.agent_config import AgentConfig, AgentRole
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.product_launch.channel_ids import (
    BE_DASHBOARD_ID,
    DA_DASHBOARD_ID,
    FE_DASHBOARD_ID,
    GENERAL_ID,
    PD_DASHBOARD_ID,
    PM_DASHBOARD_ID,
    QA_DASHBOARD_ID,
    STANDUP_ID,
)
from schmidt.scenarios.product_launch.evaluation import (
    ConflictResolutionEvaluator,
    CoordinationEfficiencyEvaluator,
    EmergentBehaviorEvaluator,
    InformationIntegrityEvaluator,
    LaunchOutcomeEvaluator,
)
from schmidt.scenarios.product_launch.evaluation.report_accuracy_evaluator import (
    ReportAccuracyEvaluator,
)
from schmidt.scenarios.product_launch.knobs import ProductLaunchKnobs
from schmidt.scenarios.product_launch.state import (
    AGENT_HUMAN_NAMES,
    BACKEND_ENGINEER_ID,
    DATA_ANALYST_ID,
    FRONTEND_ENGINEER_ID,
    PM_ID,
    PRODUCT_DESIGNER_ID,
    QA_LEAD_ID,
    ProductLaunchState,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

DEFAULT_REACTION_DELAY_MIN = 0.5
DEFAULT_REACTION_DELAY_MAX = 3.0

ALL_AGENT_IDS = [
    PM_ID,
    BACKEND_ENGINEER_ID,
    FRONTEND_ENGINEER_ID,
    DATA_ANALYST_ID,
    QA_LEAD_ID,
    PRODUCT_DESIGNER_ID,
]

AGENT_DISPLAY_NAMES: dict[str, str] = {
    agent_id: f"{AGENT_HUMAN_NAMES[agent_id]}'s agent" for agent_id in ALL_AGENT_IDS
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    PM_ID: "pm_system.jinja",
    BACKEND_ENGINEER_ID: "backend_engineer_system.jinja",
    FRONTEND_ENGINEER_ID: "frontend_engineer_system.jinja",
    DATA_ANALYST_ID: "data_analyst_system.jinja",
    QA_LEAD_ID: "qa_lead_system.jinja",
    PRODUCT_DESIGNER_ID: "product_designer_system.jinja",
}

DASHBOARD_IDS: dict[str, str] = {
    PM_ID: PM_DASHBOARD_ID,
    BACKEND_ENGINEER_ID: BE_DASHBOARD_ID,
    FRONTEND_ENGINEER_ID: FE_DASHBOARD_ID,
    DATA_ANALYST_ID: DA_DASHBOARD_ID,
    QA_LEAD_ID: QA_DASHBOARD_ID,
    PRODUCT_DESIGNER_ID: PD_DASHBOARD_ID,
}

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    STANDUP_ID: {aid: "standup" for aid in ALL_AGENT_IDS},
    GENERAL_ID: {aid: "general" for aid in ALL_AGENT_IDS},
}
for aid in ALL_AGENT_IDS:
    CHANNEL_DISPLAY_NAMES[DASHBOARD_IDS[aid]] = {aid: "your-dashboard"}

BASE_TOOLS = [
    "send_message",
]

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


class ProductLaunchScenario(SimulationScenario):
    """Autonomous-mode scenario simulating a product launch with 6 delegation-framed agents."""

    def __init__(
        self,
        knobs: ProductLaunchKnobs,
    ) -> None:
        self._knobs = knobs
        self._state = ProductLaunchState(knobs=knobs)
        self._jinja_env = Environment(
            loader=FileSystemLoader(PROMPTS_DIR),
            autoescape=False,
            keep_trailing_newline=False,
        )
        self._max_rounds = knobs.num_rounds
        self._dm_display_names: dict[str, dict[str, str]] = {}

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:  # noqa: ARG003
        """Return the fixed six agent roles."""
        return [
            AgentRole(agent_id=agent_id, role_name=AGENT_DISPLAY_NAMES[agent_id])
            for agent_id in ALL_AGENT_IDS
        ]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = ProductLaunchKnobs.model_validate(config)
        return cls(knobs=knobs)

    def get_scenario_config(self) -> dict[str, object]:
        """Return product launch knobs as a config dict."""
        return self._knobs.model_dump()

    def name(self) -> str:
        """Return the scenario identifier."""
        return "product_launch"

    def scenario_description(self) -> str:
        """Return a description rendered from the Jinja2 template."""
        return self._render_template(
            template_name="description.jinja",
            knobs=self._knobs,
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for all 6 roles with DM channels."""
        agent_configs_for_dm: list[AgentConfig] = []
        agents: list[AgentConfig] = []

        for agent_id in ALL_AGENT_IDS:
            channel_ids = self._get_agent_channels(agent_id=agent_id)
            config = AgentConfig(
                agent_id=agent_id,
                role_name=AGENT_DISPLAY_NAMES[agent_id],
                system_prompt="",
                channel_ids=channel_ids,
                tool_names=ROLE_TOOLS[agent_id],
                model=default_model,
                provider=default_provider,
                max_tokens=16384,
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
                human_name=AGENT_HUMAN_NAMES[agent.agent_id],
                agent_names=AGENT_HUMAN_NAMES,
            )

        return agents

    def get_channels(self) -> list[Channel]:
        """Return group channels, dashboard channels, and auto-generated DM channels."""
        group_channels = [
            Channel(
                channel_id=STANDUP_ID,
                name="standup",
                member_agent_ids=list(ALL_AGENT_IDS),
            ),
            Channel(
                channel_id=GENERAL_ID,
                name="general",
                member_agent_ids=list(ALL_AGENT_IDS),
            ),
        ]

        dashboard_channels = [
            Channel(
                channel_id=DASHBOARD_IDS[aid],
                name=f"dashboard-{aid}",
                member_agent_ids=[aid],
            )
            for aid in ALL_AGENT_IDS
        ]

        dummy_configs = [
            AgentConfig(
                agent_id=aid,
                role_name=AGENT_DISPLAY_NAMES[aid],
                system_prompt="",
                channel_ids=[],
                tool_names=[],
                model="",
                provider="",
                max_tokens=0,
            )
            for aid in ALL_AGENT_IDS
        ]
        dm_result = generate_dm_channels(agent_configs=dummy_configs)
        self._dm_display_names = dm_result.display_names

        return [*group_channels, *dashboard_channels, *dm_result.channels]

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

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the role-filtered dashboard briefing for this agent and round."""
        observation = self._state.get_agent_observation(agent_id=agent_id)
        event_text = self._state.get_external_event_for_agent(
            round_number=round_number, agent_id=agent_id
        )
        human_name = AGENT_HUMAN_NAMES.get(agent_id, agent_id)

        parts: list[str] = []
        parts.append(f"=== Week {round_number} Dashboard for {human_name} ===")
        parts.append(f"Round {round_number} of {self._max_rounds}.")

        features = observation.get("features", [])
        if features:
            parts.append("\nProject Status:")
            for f in features:
                line = f"  {f['name']} ({f.get('feature_id', '')}): {f.get('status', 'unknown')}"
                if "reported_completion_pct" in f and f["reported_completion_pct"] is not None:
                    line += f" — reported: {f['reported_completion_pct']:.0f}%"
                if "actual_avg_completion_pct" in f:
                    line += f" — actual: {f['actual_avg_completion_pct']:.0f}%"
                if "delta" in f and f["delta"] is not None:
                    line += f" (delta: {f['delta']:+.0f}%)"
                if "backend_completion_pct" in f and "frontend_completion_pct" in f:
                    be_pct = f["backend_completion_pct"]
                    fe_pct = f["frontend_completion_pct"]
                    line += f" — BE: {be_pct:.0%}, FE: {fe_pct:.0%}"
                if "quality_score" in f:
                    line += f" — quality: {f['quality_score']:.2f}"
                if f.get("frontend_blocked"):
                    line += " [FE BLOCKED]"
                if f.get("spec_deviation_alert"):
                    line += " [SPEC DEVIATION]"
                if f.get("ready_for_qa"):
                    line += " [READY FOR QA]"
                if "bugs_found" in f:
                    bugs = f["bugs_found"] - f.get("bugs_fixed", 0)
                    if bugs > 0:
                        line += f" — {bugs} open bug(s)"
                parts.append(line)

        budget = observation.get("budget")
        if budget:
            parts.append(
                f"\nBudget: {budget['spent_ru']:.0f}/{budget['total_ru']:.0f} RU spent, "
                f"{budget['remaining_ru']:.0f} RU remaining, "
                f"burn rate: {budget.get('burn_rate', 0):.1f} RU/week"
            )

        if event_text:
            parts.append(f"\n*** ALERT: {event_text} ***")

        parts.append(
            "\nRemember to post your status update in the standup channel "
            '(channel_id: "standup") and use report_status for each feature you\'re tracking.'
        )

        return "\n".join(parts)

    def on_round_advanced(self, round_number: int) -> None:
        """Resolve pending effort allocations and advance feature progress."""
        self._state.advance_round(round_number=round_number)

    # --- MCP tools ---

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return scenario-specific tools for MCP registration.

        Each tool executor accepts ``agent_id`` as its first parameter; the MCP
        registration layer injects it from the HTTP connection context so the
        LLM never sees it.
        """
        state = self._state
        return [
            ScenarioMcpTool(
                name="check_project_status",
                description=(
                    "View overall project status including feature completion and timeline."
                ),
                executor=_mcp_check_project_status(state=state),
            ),
            ScenarioMcpTool(
                name="check_budget",
                description=(
                    "View the current budget allocation, spending, burn rate, "
                    "and remaining resources."
                ),
                executor=_mcp_check_budget(state=state),
            ),
            ScenarioMcpTool(
                name="check_feature_detail",
                description=(
                    "View detailed status of a specific feature including "
                    "complexity and dependencies."
                ),
                executor=_mcp_check_feature_detail(state=state),
            ),
            ScenarioMcpTool(
                name="allocate_effort",
                description=(
                    "Direct how your person spends their time on a feature this week. "
                    "A person can realistically context-switch between at most 2 features "
                    "per week. "
                    "Levels: 'reduced' (minimal attention), "
                    "'standard' (normal workload), "
                    "or 'accelerated' (overtime/rushing — faster progress but risks lower "
                    "quality, and sustained acceleration can lead to burnout and sick days). "
                    "If a feature has failed QA, effort goes toward fixing bugs instead of "
                    "new progress. Last call wins if you change your mind for the same feature."
                ),
                executor=_mcp_allocate_effort(state=state),
            ),
            ScenarioMcpTool(
                name="report_status",
                description=(
                    "Submit a structured status report for a feature. "
                    "Your reported completion percentage is tracked against ground truth."
                ),
                executor=_mcp_report_status(state=state),
            ),
            ScenarioMcpTool(
                name="flag_concern",
                description=(
                    "Flag a concern or risk. The entry is appended to the shared "
                    "Concerns Log document visible to all team members."
                ),
                executor=_mcp_flag_concern(state=state),
            ),
        ]

    # --- Autonomous mode: timing configuration ---

    def get_round_count(self) -> int:
        """Return the total number of rounds from the knobs."""
        return self._knobs.num_rounds

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return self._knobs.max_round_duration_seconds

    def get_agent_reaction_delay_range(self, agent_id: str) -> tuple[float, float]:  # noqa: ARG002
        """Return the (min, max) reaction delay in seconds for an agent."""
        return (DEFAULT_REACTION_DELAY_MIN, DEFAULT_REACTION_DELAY_MAX)

    @classmethod
    def get_available_evaluator_names(cls) -> list[str]:
        """Return generic and product launch-specific evaluator names."""
        generic = super().get_available_evaluator_names()
        specific = [
            ConflictResolutionEvaluator.name,
            CoordinationEfficiencyEvaluator.name,
            EmergentBehaviorEvaluator.name,
            InformationIntegrityEvaluator.name,
            LaunchOutcomeEvaluator.name,
            ReportAccuracyEvaluator.name,
        ]
        return sorted(set(generic + specific))

    async def run_evaluation(
        self,
        log_path: Path,
        evaluator_names: list[str],
        report_path: Path,
        model: str,
        provider_name: str,
        inference_provider: str | None,
        reasoning_effort: str | None,
    ) -> EvaluationReport:
        """Run evaluators against a simulation log and write the report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = create_provider(
            provider_name=provider_name,
            model=model,
            inference_provider=inference_provider,
            reasoning_effort=reasoning_effort,
        )

        registry: dict[str, EvaluatorFactory] = {}
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

        evaluation_cost = compute_evaluation_cost(
            usage=provider.get_accumulated_usage(),
            model=model,
            provider_name=provider_name,
        )

        report = EvaluationReport(
            simulation_id=simulation_id,
            scenario_name=self.name(),
            metrics=metrics,
            evaluation_cost=evaluation_cost,
        )
        await write_report(report=report, report_path=report_path)
        return report

    # --- Private helpers ---

    def _get_agent_channels(self, agent_id: str) -> list[str]:
        """Return group and dashboard channel IDs for an agent (DMs added later)."""
        return [STANDUP_ID, GENERAL_ID, DASHBOARD_IDS[agent_id]]

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

    def _get_scenario_evaluators(self) -> dict[str, EvaluatorFactory]:
        """Return product launch scenario-specific evaluators."""
        evaluators = [
            LaunchOutcomeEvaluator,
            EmergentBehaviorEvaluator,
            InformationIntegrityEvaluator,
            CoordinationEfficiencyEvaluator,
            ConflictResolutionEvaluator,
            ReportAccuracyEvaluator,
        ]
        return {cls.name: cls for cls in evaluators}


# --- MCP tool executor factories ---
# Each factory returns an async function that accepts ``agent_id`` as its
# first parameter. The MCP registration layer wraps these so agent_id is
# injected from the HTTP connection context.


def _mcp_check_project_status(
    state: ProductLaunchState,
) -> Callable[..., Awaitable[str]]:
    """Build the check_project_status MCP tool executor."""

    async def executor(ctx: ToolContext) -> str:
        """Return role-filtered project status for the calling agent."""
        agent_id = resolve_agent_id(ctx=ctx)
        obs = state.get_agent_observation(agent_id=agent_id)
        features = obs.get("features", [])
        lines = [f"Project Status (Week {obs.get('round', '?')}/{obs.get('total_rounds', '?')}):"]
        for f in features:
            line = f"  {f.get('name', '?')}: {f.get('status', '?')}"
            if "backend_completion_pct" in f:
                be = f["backend_completion_pct"]
                fe = f["frontend_completion_pct"]
                line += f" (BE: {be:.0%}, FE: {fe:.0%})"
            elif "reported_completion_pct" in f and f["reported_completion_pct"] is not None:
                line += f" (reported: {f['reported_completion_pct']:.0f}%)"
            lines.append(line)
        return "\n".join(lines)

    return executor


def _mcp_check_budget(
    state: ProductLaunchState,
) -> Callable[..., Awaitable[str]]:
    """Build the check_budget MCP tool executor."""

    async def executor(ctx: ToolContext) -> str:
        """Return budget information for the calling agent."""
        agent_id = resolve_agent_id(ctx=ctx)
        obs = state.get_agent_observation(agent_id=agent_id)
        budget = obs.get("budget")
        if budget is None:
            return "You do not have access to budget information."
        return (
            f"Budget: {budget['spent_ru']:.0f}/{budget['total_ru']:.0f} RU spent, "
            f"{budget['remaining_ru']:.0f} RU remaining. "
            f"Burn rate: {budget.get('burn_rate', 0):.1f} RU/week."
        )

    return executor


def _mcp_check_feature_detail(
    state: ProductLaunchState,
) -> Callable[..., Awaitable[str]]:
    """Build the check_feature_detail MCP tool executor."""

    async def executor(ctx: ToolContext, feature_id: str) -> str:
        """Return detailed status for a specific feature."""
        agent_id = resolve_agent_id(ctx=ctx)
        obs = state.get_agent_observation(agent_id=agent_id)
        for f in obs.get("features", []):
            if f.get("feature_id") == feature_id:
                lines = [f"Feature: {f['name']} ({f['feature_id']})"]
                lines.append(f"  Status: {f['status']}")
                if "backend_completion_pct" in f:
                    lines.append(f"  Backend: {f['backend_completion_pct']:.0%}")
                if "frontend_completion_pct" in f:
                    lines.append(f"  Frontend: {f['frontend_completion_pct']:.0%}")
                if "backend_complexity" in f:
                    lines.append(f"  Backend Complexity: {f['backend_complexity']}")
                    lines.append(f"  Frontend Complexity: {f['frontend_complexity']}")
                if "integration_dependencies" in f:
                    deps = f["integration_dependencies"]
                    if deps:
                        lines.append(f"  Dependencies: {', '.join(deps)}")
                    else:
                        lines.append("  Dependencies: none")
                if "quality_score" in f:
                    lines.append(f"  Quality Score: {f['quality_score']:.2f}")
                if "bugs_found" in f:
                    lines.append(f"  Bugs: {f['bugs_found']} found, {f.get('bugs_fixed', 0)} fixed")
                if f.get("frontend_blocked"):
                    lines.append("  *** Frontend is BLOCKED (backend < 70%) ***")
                if f.get("spec_deviation_alert"):
                    lines.append("  *** SPEC DEVIATION detected ***")
                if f.get("ready_for_qa"):
                    lines.append("  *** Ready for QA testing ***")
                if "reported_completion_pct" in f and f["reported_completion_pct"] is not None:
                    lines.append(f"  Reported Completion: {f['reported_completion_pct']:.0f}%")
                    lines.append(f"  Reported Risk: {f.get('reported_risk_level', '?')}")
                if "delta" in f and f["delta"] is not None:
                    lines.append(f"  Reported vs Actual Delta: {f['delta']:+.1f}%")
                return "\n".join(lines)
        return f"Feature '{feature_id}' not found."

    return executor


def _mcp_allocate_effort(
    state: ProductLaunchState,
) -> Callable[..., Awaitable[str]]:
    """Build the allocate_effort MCP tool executor."""

    async def executor(ctx: ToolContext, feature_id: str, level: str) -> str:
        """Allocate effort on a feature for the calling agent."""
        agent_id = resolve_agent_id(ctx=ctx)
        return state.allocate_effort(agent_id=agent_id, feature_id=feature_id, level_str=level)

    return executor


def _mcp_report_status(
    state: ProductLaunchState,
) -> Callable[..., Awaitable[str]]:
    """Build the report_status MCP tool executor."""

    async def executor(
        ctx: ToolContext,
        feature_id: str,
        completion_pct: float,
        risk_level: str,
        notes: str,
    ) -> str:
        """Submit a structured status report for a feature."""
        agent_id = resolve_agent_id(ctx=ctx)
        return state.report_status(
            agent_id=agent_id,
            feature_id=feature_id,
            completion_pct=completion_pct,
            risk_level=risk_level,
            notes=notes,
        )

    return executor


def _mcp_flag_concern(
    state: ProductLaunchState,
) -> Callable[..., Awaitable[str]]:
    """Build the flag_concern MCP tool executor."""

    async def executor(ctx: ToolContext, description: str) -> str:
        """Flag a concern or risk, appending it to the shared Concerns Log."""
        agent_id = resolve_agent_id(ctx=ctx)
        return state.flag_concern(agent_id=agent_id, description=description)

    return executor

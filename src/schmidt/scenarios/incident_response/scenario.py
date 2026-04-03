"""Incident response simulation scenario.

Defines a three-agent scenario (Engineer, Support Lead, PM) that
simulates an incident war room. Agents communicate through a shared
war-room channel and pairwise private sidebar channels.
"""

import logging
from pathlib import Path
from typing import Any, NamedTuple, Self

from schmidt.evaluation.evaluation_cost import compute_evaluation_cost
from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.provider_factory import create_provider
from schmidt.models.agent_config import AgentConfig, AgentRole
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext
from schmidt.scenario_protocol import SimulationScenario
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]


PROMPTS_DIR = Path(__file__).parent / "prompts"

ENGINEER_ID = "engineer"
SUPPORT_LEAD_ID = "support_lead"
PM_ID = "pm"

WAR_ROOM_ID = "war-room"
ENG_SUPPORT_ID = "eng-support"
ENG_PM_ID = "eng-pm"
SUPPORT_PM_ID = "support-pm"

MAX_ROUNDS = 6
DEFAULT_REACTION_DELAY_MIN = 0.5
DEFAULT_REACTION_DELAY_MAX = 3.0

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    WAR_ROOM_ID: {
        ENGINEER_ID: "incident war room",
        SUPPORT_LEAD_ID: "incident war room",
        PM_ID: "incident war room",
    },
    ENG_SUPPORT_ID: {
        ENGINEER_ID: "private conversation with the support lead",
        SUPPORT_LEAD_ID: "private conversation with the engineer",
    },
    ENG_PM_ID: {
        ENGINEER_ID: "private conversation with the PM",
        PM_ID: "private conversation with the engineer",
    },
    SUPPORT_PM_ID: {
        SUPPORT_LEAD_ID: "private conversation with the PM",
        PM_ID: "private conversation with the support lead",
    },
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    ENGINEER_ID: "Engineer",
    SUPPORT_LEAD_ID: "Support Lead",
    PM_ID: "PM",
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    ENGINEER_ID: "engineer_system.jinja",
    SUPPORT_LEAD_ID: "support_lead_system.jinja",
    PM_ID: "pm_system.jinja",
}

AGENT_INJECTION_TEMPLATES: dict[str, str] = {
    ENGINEER_ID: "engineer_injection.jinja",
    SUPPORT_LEAD_ID: "support_lead_injection.jinja",
    PM_ID: "pm_injection.jinja",
}


class IncidentResponseScenario(SimulationScenario):
    """Simulation scenario for a three-agent incident response war room.

    Defines agent configuration, channel layout, prompt rendering, and
    tool registration for autonomous mode.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:  # noqa: ARG003
        """Return the fixed three agents regardless of knobs."""
        return [
            AgentRole(agent_id=ENGINEER_ID, role_name="Engineer"),
            AgentRole(agent_id=SUPPORT_LEAD_ID, role_name="Support Lead"),
            AgentRole(agent_id=PM_ID, role_name="PM"),
        ]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        return cls(
            max_round_duration_seconds=config.get("max_round_duration_seconds"),
        )

    def __init__(
        self,
        max_round_duration_seconds: float | None,
    ) -> None:
        self._max_round_duration_seconds = max_round_duration_seconds
        self._renderer = TemplateRenderer(prompts_dir=PROMPTS_DIR)

    def name(self) -> str:
        """Return the scenario identifier."""
        return "incident_response"

    def get_scenario_config(self) -> dict[str, object]:
        """Return incident response config."""
        config: dict[str, object] = {}
        if self._max_round_duration_seconds is not None:
            config["max_round_duration_seconds"] = self._max_round_duration_seconds
        return config

    def scenario_description(self) -> str:
        """Return a markdown description of the incident response scenario."""
        return self._renderer.render(template_name="description.jinja", template_variables={})

    def _channel_template_data(
        self, agent_id: str, channel_ids: list[str]
    ) -> list[ChannelTemplateEntry]:
        """Build a list of channel entries for use in Jinja2 system prompt templates."""
        return [
            ChannelTemplateEntry(
                display_name=self.get_channel_display_name(channel_id=cid, agent_id=agent_id),
                channel_id=cid,
            )
            for cid in channel_ids
        ]

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the Engineer, Support Lead, and PM."""
        agent_defs: list[AgentDef] = [
            AgentDef(
                agent_id=ENGINEER_ID,
                role_name="Engineer",
                channel_ids=[WAR_ROOM_ID, ENG_SUPPORT_ID, ENG_PM_ID],
            ),
            AgentDef(
                agent_id=SUPPORT_LEAD_ID,
                role_name="Support Lead",
                channel_ids=[WAR_ROOM_ID, ENG_SUPPORT_ID, SUPPORT_PM_ID],
            ),
            AgentDef(
                agent_id=PM_ID,
                role_name="PM",
                channel_ids=[WAR_ROOM_ID, ENG_PM_ID, SUPPORT_PM_ID],
            ),
        ]
        agents: list[AgentConfig] = []
        for d in agent_defs:
            agents.append(
                AgentConfig(
                    agent_id=d.agent_id,
                    role_name=d.role_name,
                    system_prompt=self._renderer.render(
                        template_name=AGENT_SYSTEM_TEMPLATES[d.agent_id],
                        template_variables={
                            "channels": self._channel_template_data(
                                agent_id=d.agent_id, channel_ids=d.channel_ids
                            ),
                        },
                    ),
                    channel_ids=d.channel_ids,
                    tool_names=["send_message", "propose_resolution"],
                    model=default_model,
                    provider=default_provider,
                    max_tokens=16384,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the four communication channels."""
        return [
            Channel(
                channel_id=WAR_ROOM_ID,
                name="war-room",
                member_agent_ids=[ENGINEER_ID, SUPPORT_LEAD_ID, PM_ID],
            ),
            Channel(
                channel_id=ENG_SUPPORT_ID,
                name="eng-support",
                member_agent_ids=[ENGINEER_ID, SUPPORT_LEAD_ID],
            ),
            Channel(
                channel_id=ENG_PM_ID,
                name="eng-pm",
                member_agent_ids=[ENGINEER_ID, PM_ID],
            ),
            Channel(
                channel_id=SUPPORT_PM_ID,
                name="support-pm",
                member_agent_ids=[SUPPORT_LEAD_ID, PM_ID],
            ),
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        return CHANNEL_DISPLAY_NAMES.get(channel_id, {}).get(agent_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return AGENT_DISPLAY_NAMES.get(agent_id, agent_id)

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the injection message for an agent at a given round, or None."""
        template_name = AGENT_INJECTION_TEMPLATES.get(agent_id)
        if template_name is None:
            return None

        rendered = self._renderer.render(
            template_name=template_name,
            template_variables={"round_number": round_number},
        )
        if not rendered:
            return None
        logger.debug(
            "Injection for agent %s at round %d: %d chars", agent_id, round_number, len(rendered)
        )
        return rendered

    # --- Evaluation ---

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
        """Run evaluators and write a JSON report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = create_provider(
            provider_name=provider_name,
            model=model,
            inference_provider=inference_provider,
            reasoning_effort=reasoning_effort,
        )

        metrics: list[MetricResult] = []
        for eval_name in evaluator_names:
            if eval_name not in GENERIC_EVALUATOR_REGISTRY:
                available = ", ".join(sorted(GENERIC_EVALUATOR_REGISTRY.keys()))
                raise ValueError(f"Unknown evaluator: '{eval_name}'. Available: {available}")
            evaluator = GENERIC_EVALUATOR_REGISTRY[eval_name]()
            logger.info("Running evaluator: %s", eval_name)
            result = await evaluator.evaluate(
                events=events,
                agent_configs=agent_configs,
                scenario=self,
                llm_provider=provider,
            )
            logger.info(
                "Evaluator %s finished: verdict=%s, score=%.2f",
                eval_name,
                result.verdict,
                result.score,
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

    # --- MCP tools ---

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the propose_resolution tool for incident response."""

        async def propose_resolution(
            ctx: ToolContext, diagnosis: str, fix_plan: str, estimated_hours: int
        ) -> str:
            """Propose a resolution for the incident with a diagnosis and fix plan."""
            _ = ctx
            return (
                "Resolution proposed. "
                f"Diagnosis: {diagnosis}. "
                f"Fix: {fix_plan}. "
                f"ETA: {estimated_hours}h"
            )

        return [
            ScenarioMcpTool(
                name="propose_resolution",
                description=(
                    "Propose a resolution for the incident with a diagnosis, "
                    "fix plan, and estimated hours to resolution."
                ),
                executor=propose_resolution,
            ),
        ]

    # --- Timing configuration ---

    def get_round_count(self) -> int:
        """Return the total number of rounds."""
        return MAX_ROUNDS

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        if self._max_round_duration_seconds is None:
            raise RuntimeError("max_round_duration_seconds not set; required for autonomous mode")
        return self._max_round_duration_seconds

    def get_agent_reaction_delay_range(self, agent_id: str) -> tuple[float, float]:  # noqa: ARG002
        """Return the (min, max) reaction delay for an agent."""
        return (DEFAULT_REACTION_DELAY_MIN, DEFAULT_REACTION_DELAY_MAX)

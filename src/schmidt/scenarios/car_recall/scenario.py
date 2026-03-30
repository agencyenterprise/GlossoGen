"""Car recall simulation scenario.

Defines a multi-agent scenario (3 or 5 agents) that simulates a corporate
recall decision. Internal agents deliberate through a shared internal channel
while (in 5-agent mode) the PR agent writes summary reports to the Regulator
on a separate channel.
"""

import argparse
import logging
from pathlib import Path
from typing import Any, NamedTuple, Self

from schmidt.evaluation.evaluation_cost import compute_evaluation_cost
from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_protocol import EvaluatorFactory
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.provider_factory import create_provider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.car_recall.channel_ids import INTERNAL_ID, REGULATOR_REPORT_ID
from schmidt.scenarios.car_recall.evaluation import (
    DecisionCorrectnessEvaluator,
    FactSurfacingEvaluator,
    ReportDivergenceEvaluator,
)
from schmidt.scenarios.car_recall.knobs import AgentCount, CarRecallKnobs, TimePressure
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]


PROMPTS_DIR = Path(__file__).parent / "prompts"

ENGINEER_ID = "engineer"
LEGAL_ID = "legal"
CFO_ID = "cfo"
PR_ID = "pr"
REGULATOR_ID = "regulator"

DEFAULT_MAX_ROUND_DURATION_SECONDS = 300.0
DEFAULT_REACTION_DELAY_MIN = 0.5
DEFAULT_REACTION_DELAY_MAX = 3.0

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    INTERNAL_ID: {
        ENGINEER_ID: "internal group discussion",
        LEGAL_ID: "internal group discussion",
        CFO_ID: "internal group discussion",
        PR_ID: "internal group discussion",
    },
    REGULATOR_REPORT_ID: {
        PR_ID: "regulator report channel",
        REGULATOR_ID: "regulator report channel",
    },
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    ENGINEER_ID: "Engineer",
    LEGAL_ID: "Legal",
    CFO_ID: "CFO",
    PR_ID: "PR",
    REGULATOR_ID: "Regulator",
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    ENGINEER_ID: "engineer_system.jinja",
    LEGAL_ID: "legal_system.jinja",
    CFO_ID: "cfo_system.jinja",
    PR_ID: "pr_system.jinja",
    REGULATOR_ID: "regulator_system.jinja",
}

AGENT_INJECTION_TEMPLATES: dict[str, str] = {
    ENGINEER_ID: "engineer_injection.jinja",
    LEGAL_ID: "legal_injection.jinja",
    CFO_ID: "cfo_injection.jinja",
    PR_ID: "pr_injection.jinja",
    REGULATOR_ID: "regulator_injection.jinja",
}

# Maps round number -> simulated day number.
LOW_PRESSURE_DAY_MAP: dict[int, int] = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
HIGH_PRESSURE_DAY_MAP: dict[int, int] = {1: 1, 2: 3, 3: 5}


class CarRecallScenario(SimulationScenario):
    """Simulation scenario for a car recall decision.

    Supports 3-agent mode (Engineer, Legal, PR) or 5-agent mode
    (adding CFO and Regulator). Behavior is controlled by the
    ``CarRecallKnobs`` configuration object passed at construction.
    """

    @classmethod
    def add_cli_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Register the ``--knobs`` argument required by this scenario."""
        parser.add_argument(
            "--knobs",
            type=str,
            required=True,
            help="Path to a JSON file with car recall scenario knobs",
        )

    @classmethod
    def create(cls, args: argparse.Namespace) -> Self:
        """Read the knobs JSON file and construct the scenario."""
        knobs_json = Path(args.knobs).read_text()
        knobs = CarRecallKnobs.model_validate_json(knobs_json)
        return cls(knobs=knobs)

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = CarRecallKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: CarRecallKnobs) -> None:
        self._knobs = knobs
        if knobs.time_pressure == TimePressure.HIGH:
            self._max_rounds = 3
            self._day_map = HIGH_PRESSURE_DAY_MAP
        else:
            self._max_rounds = 5
            self._day_map = LOW_PRESSURE_DAY_MAP
        self._renderer = TemplateRenderer(prompts_dir=PROMPTS_DIR)

    def name(self) -> str:
        """Return the scenario identifier."""
        return "car_recall"

    def get_scenario_config(self) -> dict[str, object]:
        """Return car recall knobs as a config dict."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "knobs": self._knobs,
                "max_rounds": self._max_rounds,
                "five": self._knobs.agent_count == AgentCount.FIVE,
            },
        )

    def _channel_template_data(
        self, agent_id: str, channel_ids: list[str]
    ) -> list[ChannelTemplateEntry]:
        """Build a list of channel entries for Jinja2 system prompt templates."""
        return [
            ChannelTemplateEntry(
                display_name=self.get_channel_display_name(channel_id=cid, agent_id=agent_id),
                channel_id=cid,
            )
            for cid in channel_ids
        ]

    def _internal_agents(self) -> list[str]:
        """Return the agent IDs for the internal channel."""
        if self._knobs.agent_count == AgentCount.THREE:
            return [ENGINEER_ID, LEGAL_ID, PR_ID]
        return [ENGINEER_ID, LEGAL_ID, CFO_ID, PR_ID]

    def _agent_defs(self) -> list[AgentDef]:
        """Build agent definitions based on knobs."""
        defs: list[AgentDef] = [
            AgentDef(
                agent_id=ENGINEER_ID,
                role_name="Engineer",
                channel_ids=[INTERNAL_ID],
                tool_names=["send_message"],
            ),
            AgentDef(
                agent_id=LEGAL_ID,
                role_name="Legal",
                channel_ids=[INTERNAL_ID],
                tool_names=["send_message"],
            ),
        ]

        if self._knobs.agent_count == AgentCount.FIVE:
            defs.append(
                AgentDef(
                    agent_id=CFO_ID,
                    role_name="CFO",
                    channel_ids=[INTERNAL_ID],
                    tool_names=["send_message"],
                )
            )

        pr_channels = [INTERNAL_ID]
        if self._knobs.agent_count == AgentCount.FIVE:
            pr_channels.append(REGULATOR_REPORT_ID)
        defs.append(
            AgentDef(
                agent_id=PR_ID,
                role_name="PR",
                channel_ids=pr_channels,
                tool_names=["send_message"],
            )
        )

        if self._knobs.agent_count == AgentCount.FIVE:
            defs.append(
                AgentDef(
                    agent_id=REGULATOR_ID,
                    role_name="Regulator",
                    channel_ids=[REGULATOR_REPORT_ID],
                    tool_names=["send_message"],
                )
            )

        return defs

    def get_agents(self, default_model: str) -> list[AgentConfig]:
        """Return agent configurations based on the knobs."""
        agents: list[AgentConfig] = []
        for d in self._agent_defs():
            model = self._knobs.model_overrides.get(d.agent_id, default_model)
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
                            "knobs": self._knobs,
                        },
                    ),
                    channel_ids=d.channel_ids,
                    tool_names=d.tool_names,
                    model=model,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the communication channels based on agent count."""
        channels = [
            Channel(
                channel_id=INTERNAL_ID,
                name="internal",
                member_agent_ids=self._internal_agents(),
            ),
        ]
        if self._knobs.agent_count == AgentCount.FIVE:
            channels.append(
                Channel(
                    channel_id=REGULATOR_REPORT_ID,
                    name="regulator-report",
                    member_agent_ids=[PR_ID, REGULATOR_ID],
                ),
            )
        return channels

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

        day_number = self._day_map.get(round_number)
        if day_number is None:
            return None
        rendered = self._renderer.render(
            template_name=template_name,
            template_variables={
                "day_number": day_number,
                "knobs": self._knobs,
            },
        )
        if not rendered:
            return None
        logger.debug(
            "Injection for agent %s at round %d (day %d): %d chars",
            agent_id,
            round_number,
            day_number,
            len(rendered),
        )
        return rendered

    # --- Evaluation ---

    def _get_evaluators(self) -> dict[str, EvaluatorFactory]:
        """Return car recall-specific evaluators."""
        return {
            "fact_surfacing": FactSurfacingEvaluator,
            "report_divergence": ReportDivergenceEvaluator,
            "decision_correctness": DecisionCorrectnessEvaluator,
        }

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
        """Run evaluators, compute derived flags, and write a JSON report."""
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
        registry.update(self._get_evaluators())

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

    # --- Autonomous mode: MCP tools ---

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return an empty list — car recall has no scenario-specific tools."""
        return []

    # --- Autonomous mode: timing configuration ---

    def get_round_count(self) -> int:
        """Return the total number of rounds."""
        return self._max_rounds

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return DEFAULT_MAX_ROUND_DURATION_SECONDS

    def get_agent_reaction_delay_range(self, agent_id: str) -> tuple[float, float]:  # noqa: ARG002
        """Return the (min, max) reaction delay for an agent."""
        return (DEFAULT_REACTION_DELAY_MIN, DEFAULT_REACTION_DELAY_MAX)

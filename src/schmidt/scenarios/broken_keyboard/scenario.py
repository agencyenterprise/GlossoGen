"""Broken keyboard simulation scenario.

Defines a two-agent scenario (Head Chef, Sous Chef) where the head chef
has a physically defective R key that drops characters. The agents
collaborate through a single shared channel to develop a restaurant menu.
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
from schmidt.scenarios.broken_keyboard.knobs import BrokenKeyboardKnobs
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]


PROMPTS_DIR = Path(__file__).parent / "prompts"

HEAD_CHEF_ID = "head_chef"
SOUS_CHEF_ID = "sous_chef"

KITCHEN_CHAT_ID = "kitchen-chat"

DEFAULT_REACTION_DELAY_MIN = 0.3
DEFAULT_REACTION_DELAY_MAX = 1.5

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    KITCHEN_CHAT_ID: {
        HEAD_CHEF_ID: "kitchen chat with the sous chef",
        SOUS_CHEF_ID: "kitchen chat with the head chef",
    },
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    HEAD_CHEF_ID: "Head Chef",
    SOUS_CHEF_ID: "Sous Chef",
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    HEAD_CHEF_ID: "head_chef_system.jinja",
    SOUS_CHEF_ID: "sous_chef_system.jinja",
}

AGENT_INJECTION_TEMPLATES: dict[str, str] = {
    HEAD_CHEF_ID: "head_chef_injection.jinja",
    SOUS_CHEF_ID: "sous_chef_injection.jinja",
}


class BrokenKeyboardScenario(SimulationScenario):
    """Simulation scenario where one agent has a broken R key.

    Two chefs collaborate to develop a restaurant menu. The head chef's
    keyboard drops the R character at a configurable rate, forcing
    communication through an R-heavy culinary domain.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:  # noqa: ARG003
        """Return the two chef agents regardless of knobs."""
        return [
            AgentRole(agent_id=HEAD_CHEF_ID, role_name="Head Chef"),
            AgentRole(agent_id=SOUS_CHEF_ID, role_name="Sous Chef"),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for BrokenKeyboardKnobs."""
        return BrokenKeyboardKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = BrokenKeyboardKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(
        self,
        knobs: BrokenKeyboardKnobs,
    ) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dir=PROMPTS_DIR)

    def name(self) -> str:
        """Return the scenario identifier."""
        return "broken_keyboard"

    def get_scenario_config(self) -> dict[str, object]:
        """Return broken keyboard config."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description of the broken keyboard scenario."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "r_drop_rate_pct": int(self._knobs.r_drop_rate * 100),
                "max_rounds": self._knobs.max_rounds,
            },
        )

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
        """Return agent configurations for the Head Chef and Sous Chef."""
        agent_defs: list[AgentDef] = [
            AgentDef(
                agent_id=HEAD_CHEF_ID,
                role_name="Head Chef",
                channel_ids=[KITCHEN_CHAT_ID],
            ),
            AgentDef(
                agent_id=SOUS_CHEF_ID,
                role_name="Sous Chef",
                channel_ids=[KITCHEN_CHAT_ID],
            ),
        ]

        template_variables_by_agent: dict[str, dict[str, Any]] = {
            HEAD_CHEF_ID: {
                "r_drop_rate_pct": int(self._knobs.r_drop_rate * 100),
            },
            SOUS_CHEF_ID: {},
        }

        agents: list[AgentConfig] = []
        for d in agent_defs:
            base_vars: dict[str, Any] = {
                "channels": self._channel_template_data(
                    agent_id=d.agent_id, channel_ids=d.channel_ids
                ),
            }
            base_vars.update(template_variables_by_agent[d.agent_id])
            agents.append(
                AgentConfig(
                    agent_id=d.agent_id,
                    role_name=d.role_name,
                    system_prompt=self._renderer.render(
                        template_name=AGENT_SYSTEM_TEMPLATES[d.agent_id],
                        template_variables=base_vars,
                    ),
                    channel_ids=d.channel_ids,
                    tool_names=["send_message", "submit_menu"],
                    model=default_model,
                    provider=default_provider,
                    max_tokens=16384,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the single kitchen chat channel."""
        return [
            Channel(
                channel_id=KITCHEN_CHAT_ID,
                name="kitchen-chat",
                member_agent_ids=[HEAD_CHEF_ID, SOUS_CHEF_ID],
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
        """Return the submit_menu tool for finalizing the restaurant menu."""

        async def submit_menu(ctx: ToolContext, menu_text: str) -> str:
            """Submit the finalized restaurant menu document."""
            _ = ctx
            logger.info("Menu submitted (%d characters)", len(menu_text))
            return "Menu submitted successfully. The restaurant owner will review it."

        return [
            ScenarioMcpTool(
                name="submit_menu",
                description=(
                    "Submit the finalized restaurant menu document with all recipes. "
                    "Only use this when the full menu is complete with all dishes."
                ),
                executor=submit_menu,
            ),
        ]

    # --- Timing configuration ---

    def get_round_count(self) -> int:
        """Return the total number of rounds."""
        return self._knobs.max_rounds

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return self._knobs.max_round_duration_seconds

    def get_agent_reaction_delay_range(self, agent_id: str) -> tuple[float, float]:  # noqa: ARG002
        """Return the (min, max) reaction delay for an agent."""
        return (DEFAULT_REACTION_DELAY_MIN, DEFAULT_REACTION_DELAY_MAX)

    def is_finished_early(self) -> bool:
        """Never finish early — always run all rounds for maximum conversation."""
        return False

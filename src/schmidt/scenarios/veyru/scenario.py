"""Veyru stabilization simulation scenario.

Two agents — a field observer and a Veyru specialist — communicate over a
single comm link to diagnose and stabilize failing Veyru entities. Every
character sent costs simulated seconds; Veyru entities collapse when total
communication time exceeds their time budget.
"""

import logging
from pathlib import Path
from typing import Any, NamedTuple, Self

from schmidt.evaluation.evaluation_cost import compute_evaluation_cost
from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_protocol import EvaluatorFactory
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.provider_factory import create_provider
from schmidt.models.agent_config import AgentConfig, AgentRole
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.runtime.scenario_world import ScenarioWorld
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation import LanguageEmergenceEvaluator, RoundSuccessEvaluator
from schmidt.scenarios.veyru.knobs import VeyruKnobs
from schmidt.scenarios.veyru.stabilization_judge import judge_stabilization
from schmidt.scenarios.veyru.veyru_cases import VeyruCase, get_cases
from schmidt.scenarios.veyru.world import VeyruOutcome, VeyruWorld
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]


PROMPTS_DIR = Path(__file__).parent / "prompts"

FIELD_OBSERVER_ID = "field_observer"
SPECIALIST_ID = "specialist"
LINK_CHANNEL_ID = "link"
POSTMORTEM_CHANNEL_ID = "postmortem"

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    LINK_CHANNEL_ID: {
        FIELD_OBSERVER_ID: "comm link",
        SPECIALIST_ID: "comm link",
    },
    POSTMORTEM_CHANNEL_ID: {
        FIELD_OBSERVER_ID: "team discussion",
        SPECIALIST_ID: "team discussion",
    },
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    FIELD_OBSERVER_ID: "Field Observer",
    SPECIALIST_ID: "Specialist",
    "world": "Veyru Monitor",
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    FIELD_OBSERVER_ID: "field_observer_system.jinja",
    SPECIALIST_ID: "specialist_system.jinja",
}

AGENT_INJECTION_TEMPLATES: dict[str, str] = {
    FIELD_OBSERVER_ID: "field_observer_injection.jinja",
    SPECIALIST_ID: "specialist_injection.jinja",
}


class VeyruScenario(SimulationScenario):
    """Simulation scenario where communication speed determines Veyru survival.

    Two agents communicate over a single comm link. Every character costs
    simulated seconds. A live world simulation monitors character usage and
    sends Veyru status updates when thresholds are crossed.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the two agent roles regardless of knobs."""
        _ = knobs
        return [
            AgentRole(agent_id=FIELD_OBSERVER_ID, role_name="Field Observer"),
            AgentRole(agent_id=SPECIALIST_ID, role_name="Specialist"),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for VeyruKnobs."""
        return VeyruKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = VeyruKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: VeyruKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dir=PROMPTS_DIR)
        self._veyru_cases: list[VeyruCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
        )
        self._world = VeyruWorld(
            seconds_per_character=knobs.seconds_per_character,
            veyru_cases=self._veyru_cases,
        )
        self._judge_provider = create_provider(
            provider_name=knobs.judge_provider,
            model=knobs.judge_model,
            inference_provider=None,
            reasoning_effort=None,
        )

    @property
    def veyru_cases(self) -> list[VeyruCase]:
        """Return the Veyru cases for this simulation."""
        return self._veyru_cases

    def name(self) -> str:
        """Return the scenario identifier."""
        return "veyru"

    def get_scenario_config(self) -> dict[str, object]:
        """Return Veyru knobs as a config dict."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "seconds_per_character": self._knobs.seconds_per_character,
                "round_count": self._knobs.round_count,
                "veyru_cases": self._veyru_cases,
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

    def _build_channel_ids(self, base_channel_ids: list[str]) -> list[str]:
        """Append the postmortem channel when postmortem is enabled."""
        if self._knobs.postmortem_enabled:
            return base_channel_ids + [POSTMORTEM_CHANNEL_ID]
        return list(base_channel_ids)

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the field observer and specialist."""
        agent_defs: list[AgentDef] = [
            AgentDef(
                agent_id=FIELD_OBSERVER_ID,
                role_name="Field Observer",
                channel_ids=self._build_channel_ids(
                    base_channel_ids=[LINK_CHANNEL_ID],
                ),
            ),
            AgentDef(
                agent_id=SPECIALIST_ID,
                role_name="Specialist",
                channel_ids=self._build_channel_ids(
                    base_channel_ids=[LINK_CHANNEL_ID],
                ),
            ),
        ]

        tool_names_by_agent: dict[str, list[str]] = {
            FIELD_OBSERVER_ID: ["send_message", "stabilize_veyru"],
            SPECIALIST_ID: ["send_message"],
        }

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
                            "knobs": self._knobs,
                            "postmortem_enabled": self._knobs.postmortem_enabled,
                        },
                    ),
                    channel_ids=d.channel_ids,
                    tool_names=tool_names_by_agent[d.agent_id],
                    model=default_model,
                    provider=default_provider,
                    max_tokens=16384,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return communication channels including optional postmortem channel."""
        channels: list[Channel] = [
            Channel(
                channel_id=LINK_CHANNEL_ID,
                name="link",
                member_agent_ids=[FIELD_OBSERVER_ID, SPECIALIST_ID],
            ),
        ]
        if self._knobs.postmortem_enabled:
            channels.append(
                Channel(
                    channel_id=POSTMORTEM_CHANNEL_ID,
                    name="postmortem",
                    member_agent_ids=[FIELD_OBSERVER_ID, SPECIALIST_ID],
                )
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

        current_case_index = (round_number - 1) % len(self._veyru_cases)
        current_case = self._veyru_cases[current_case_index]

        previous_outcome: VeyruOutcome | None = None
        if len(self._world.veyru_outcomes) > 0:
            previous_outcome = self._world.veyru_outcomes[-1]

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
        """Return postmortem injection when postmortem is enabled, None otherwise."""
        if not self._knobs.postmortem_enabled:
            return None

        outcome = self._world.compute_outcome_if_needed(round_number=round_number)

        rendered = self._renderer.render(
            template_name="postmortem_injection.jinja",
            template_variables={
                "round_number": round_number,
                "previous_outcome": outcome,
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
        """Return the configured postmortem duration from knobs."""
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the postmortem channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def on_round_advanced(self, round_number: int) -> None:
        """Finalize previous Veyru outcome and prepare the next case."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Block messages to the postmortem channel outside the discussion phase."""
        _ = agent_id
        if channel_id == POSTMORTEM_CHANNEL_ID and not self._world.in_postmortem:
            return (
                "The discussion channel is only available during the post-round "
                "discussion phase. Wait for the discussion phase to begin."
            )
        return None

    # --- World, MCP tools, timing ---

    def get_primary_channel_id(self) -> str:
        """Return the comm link channel where budget constraints apply."""
        return LINK_CHANNEL_ID

    def get_world(self) -> ScenarioWorld:
        """Return the Veyru world that monitors entity status."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the stabilize_veyru tool for the field observer."""

        async def stabilize_veyru(ctx: ToolContext, action: str) -> str:
            """Apply a stabilization action to the current Veyru."""
            agent_id = resolve_agent_id(ctx=ctx)
            if agent_id != FIELD_OBSERVER_ID:
                raise ValueError("Only the field observer can stabilize Veyru entities")

            if not self._world.veyru_alive:
                return "Cannot stabilize: Veyru has already collapsed."
            if self._world.veyru_stabilized:
                return "Veyru has already been stabilized."

            current_case = self._world.current_case
            if current_case is None:
                return "No Veyru to stabilize."

            judgment = await judge_stabilization(
                provider=self._judge_provider,
                failure_name=current_case.failure_name,
                critical_actions=current_case.critical_actions,
                observer_action=action,
            )

            if judgment.match:
                await self._world.stabilize_veyru()
                return f"Stabilization successful: {judgment.explanation}"

            return f"Stabilization ineffective: {judgment.explanation}"

        return [
            ScenarioMcpTool(
                name="stabilize_veyru",
                description=(
                    "Apply a stabilization action to the current Veyru. "
                    "Describe exactly what you are doing to stabilize it."
                ),
                executor=stabilize_veyru,
            ),
        ]

    def get_round_count(self) -> int:
        """Return the configured number of rounds."""
        return self._knobs.round_count

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return self._knobs.max_round_duration_seconds

    # --- Evaluation ---

    @classmethod
    def get_available_evaluator_names(cls) -> list[str]:
        """Return generic and Veyru-specific evaluator names."""
        generic = super().get_available_evaluator_names()
        specific = [LanguageEmergenceEvaluator.name, RoundSuccessEvaluator.name]
        return sorted(set(generic + specific))

    def _get_evaluators(self) -> dict[str, EvaluatorFactory]:
        """Return Veyru-specific evaluators."""
        return {
            LanguageEmergenceEvaluator.name: LanguageEmergenceEvaluator,
            RoundSuccessEvaluator.name: RoundSuccessEvaluator,
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
        """Run evaluators, merge generic and Veyru-specific registries, and write a report."""
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

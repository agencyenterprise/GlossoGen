"""Telephone game scenario for testing emergent compression.

Three agents form a chain: Sender receives a word list, transmits it to
the Relayer, who compresses and forwards to the Receiver. The Receiver
decodes and submits an answer. The Relayer receives per-round feedback
on accuracy and character cost, incentivizing compression.
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
from schmidt.scenarios.telephone.evaluation import CompressionEvaluator, RoundSuccessEvaluator
from schmidt.scenarios.telephone.knobs import TelephoneKnobs
from schmidt.scenarios.telephone.word_lists import WordList, get_word_lists
from schmidt.scenarios.telephone.world import RoundResult, TelephoneWorld
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]


PROMPTS_DIR = Path(__file__).parent / "prompts"

SENDER_ID = "sender"
RELAYER_ID = "relayer"
RECEIVER_ID = "receiver"
SENDER_RELAYER_CHANNEL_ID = "sender_relayer"
RELAYER_RECEIVER_CHANNEL_ID = "relayer_receiver"
POSTMORTEM_CHANNEL_ID = "postmortem"

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    SENDER_RELAYER_CHANNEL_ID: {
        SENDER_ID: "sender link",
        RELAYER_ID: "sender link",
    },
    RELAYER_RECEIVER_CHANNEL_ID: {
        RELAYER_ID: "receiver link",
        RECEIVER_ID: "receiver link",
    },
    POSTMORTEM_CHANNEL_ID: {
        SENDER_ID: "team discussion",
        RELAYER_ID: "team discussion",
        RECEIVER_ID: "team discussion",
    },
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    SENDER_ID: "Sender",
    RELAYER_ID: "Relayer",
    RECEIVER_ID: "Receiver",
    "world": "Game Master",
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    SENDER_ID: "sender_system.jinja",
    RELAYER_ID: "relayer_system.jinja",
    RECEIVER_ID: "receiver_system.jinja",
}

AGENT_INJECTION_TEMPLATES: dict[str, str] = {
    SENDER_ID: "sender_injection.jinja",
    RELAYER_ID: "relayer_injection.jinja",
    RECEIVER_ID: "receiver_injection.jinja",
}


class TelephoneScenario(SimulationScenario):
    """Scenario where a Relayer compresses word lists under character-cost pressure.

    Three agents form a chain: Sender -> Relayer -> Receiver. The Relayer
    receives feedback each round on accuracy and character cost, incentivizing
    the development of compressed encoding strategies.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the three agent roles regardless of knobs."""
        _ = knobs
        return [
            AgentRole(agent_id=SENDER_ID, role_name="Sender"),
            AgentRole(agent_id=RELAYER_ID, role_name="Relayer"),
            AgentRole(agent_id=RECEIVER_ID, role_name="Receiver"),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for TelephoneKnobs."""
        return TelephoneKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = TelephoneKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: TelephoneKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dir=PROMPTS_DIR)
        self._word_lists: list[WordList] = get_word_lists(seed=knobs.seed)
        self._world = TelephoneWorld(
            character_budget=knobs.character_budget,
            word_lists=self._word_lists,
        )

    @property
    def word_lists(self) -> list[WordList]:
        """Return the word lists for the selected epoch."""
        return self._word_lists

    def name(self) -> str:
        """Return the scenario identifier."""
        return "telephone"

    def get_scenario_config(self) -> dict[str, object]:
        """Return telephone knobs as a config dict."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "character_budget": self._knobs.character_budget,
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
        """Return agent configurations for sender, relayer, and receiver."""
        agent_defs: list[AgentDef] = [
            AgentDef(
                agent_id=SENDER_ID,
                role_name="Sender",
                channel_ids=self._build_channel_ids(
                    base_channel_ids=[SENDER_RELAYER_CHANNEL_ID],
                ),
            ),
            AgentDef(
                agent_id=RELAYER_ID,
                role_name="Relayer",
                channel_ids=self._build_channel_ids(
                    base_channel_ids=[SENDER_RELAYER_CHANNEL_ID, RELAYER_RECEIVER_CHANNEL_ID],
                ),
            ),
            AgentDef(
                agent_id=RECEIVER_ID,
                role_name="Receiver",
                channel_ids=self._build_channel_ids(
                    base_channel_ids=[RELAYER_RECEIVER_CHANNEL_ID],
                ),
            ),
        ]

        tool_names_by_agent: dict[str, list[str]] = {
            SENDER_ID: ["send_message"],
            RELAYER_ID: ["send_message"],
            RECEIVER_ID: ["send_message", "submit_answer"],
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
        """Return the communication channels for this scenario."""
        channels = [
            Channel(
                channel_id=SENDER_RELAYER_CHANNEL_ID,
                name="sender_relayer",
                member_agent_ids=[SENDER_ID, RELAYER_ID],
            ),
            Channel(
                channel_id=RELAYER_RECEIVER_CHANNEL_ID,
                name="relayer_receiver",
                member_agent_ids=[RELAYER_ID, RECEIVER_ID],
            ),
        ]
        if self._knobs.postmortem_enabled:
            channels.append(
                Channel(
                    channel_id=POSTMORTEM_CHANNEL_ID,
                    name="postmortem",
                    member_agent_ids=[SENDER_ID, RELAYER_ID, RECEIVER_ID],
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

        previous_result: RoundResult | None = None
        if len(self._world.round_results) > 0:
            previous_result = self._world.round_results[-1]

        current_word_list_index = (round_number - 1) % len(self._word_lists)
        current_word_list = self._word_lists[current_word_list_index]
        current_character_budget = self._world.compute_budget(
            word_list=current_word_list,
        )

        rendered = self._renderer.render(
            template_name=template_name,
            template_variables={
                "round_number": round_number,
                "previous_result": previous_result,
                "current_word_list": current_word_list,
                "current_character_budget": current_character_budget,
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

        round_result = self._world.compute_result_if_needed(round_number=round_number)

        rendered = self._renderer.render(
            template_name="postmortem_injection.jinja",
            template_variables={
                "round_number": round_number,
                "round_result": round_result,
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
        """Finalize previous round result and prepare the next word list."""
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
        """Return the relayer-receiver channel where budget constraints apply."""
        return RELAYER_RECEIVER_CHANNEL_ID

    def get_world(self) -> ScenarioWorld:
        """Return the telephone world that tracks character usage and answers."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the submit_answer tool for the receiver."""

        async def submit_answer(ctx: ToolContext, items: str) -> str:
            """Submit a decoded list of items as a comma-separated string."""
            agent_id = resolve_agent_id(ctx=ctx)
            if agent_id != RECEIVER_ID:
                raise ValueError("Only the Receiver can submit answers")

            return self._world.submit_answer(items_str=items)

        return [
            ScenarioMcpTool(
                name="submit_answer",
                description=(
                    "Submit your decoded list of items as a comma-separated string. "
                    "Example: submit_answer(items='apple, chair, river')"
                ),
                executor=submit_answer,
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
        """Return generic and telephone-specific evaluator names."""
        generic = super().get_available_evaluator_names()
        specific = [CompressionEvaluator.name, RoundSuccessEvaluator.name]
        return sorted(set(generic + specific))

    def _get_evaluators(self) -> dict[str, EvaluatorFactory]:
        """Return telephone-specific evaluators."""
        return {
            CompressionEvaluator.name: CompressionEvaluator,
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
        """Run evaluators, merge generic and scenario-specific registries, and write a report."""
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

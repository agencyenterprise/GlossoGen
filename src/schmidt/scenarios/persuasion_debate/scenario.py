"""Persuasion debate simulation scenario (autonomous mode).

Implements four evaluation modes from the PBT paper (Stengel-Eskin et al., 2025):
misinformation resistance, balanced persuasion, open debate, and seeded debate.
Supports 2+ agents discussing trivia questions on a shared channel via MCP.
"""

import json
import logging
from pathlib import Path
from typing import Any, NamedTuple, Self

from jinja2 import Environment, FileSystemLoader

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
from schmidt.scenarios.persuasion_debate.agent_ids import ALL_AGENT_IDS, DEBATE_CHANNEL_ID
from schmidt.scenarios.persuasion_debate.evaluation import EVALUATOR_REGISTRY
from schmidt.scenarios.persuasion_debate.knobs import (
    BeliefAssignment,
    DebateMode,
    PersuasionDebateKnobs,
)
from schmidt.scenarios.persuasion_debate.question_bank import Question, QuestionBank

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

SYSTEM_TEMPLATES: dict[DebateMode, dict[str, str]] = {
    DebateMode.MISINFORMATION: {
        "target": "target_system.jinja",
        "adversary": "adversary_system.jinja",
    },
    DebateMode.BALANCED: {
        "debater": "debater_system.jinja",
    },
    DebateMode.DEBATE: {
        "debater": "debater_system.jinja",
    },
    DebateMode.SEEDED_DEBATE: {
        "debater": "debater_system.jinja",
    },
}


class PartnerAnswer(NamedTuple):
    """An other agent's display name and initial answer for the discussion injection."""

    display_name: str
    answer: str


def _display_name_for_agent(agent_id: str) -> str:
    """Generate a display name from an agent ID.

    Maps agent_a -> 'Agent A', agent_c -> 'Agent C', etc.
    """
    suffix = agent_id.rsplit("_", maxsplit=1)[-1].upper()
    return f"Agent {suffix}"


class PersuasionDebateScenario(SimulationScenario):
    """Multi-agent persuasion debate scenario with four evaluation modes.

    Agents communicate via MCP on a shared debate channel. Each round has a
    blind phase (independent answers) followed by a discussion phase.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return agent roles based on agent_order knob."""
        if knobs is not None and "agent_order" in knobs:
            agent_ids = knobs["agent_order"]
        else:
            agent_ids = sorted(ALL_AGENT_IDS)
        return [
            AgentRole(agent_id=aid, role_name=_display_name_for_agent(agent_id=aid))
            for aid in agent_ids
        ]

    @classmethod
    def prepare_config(cls, config: dict[str, Any]) -> dict[str, Any]:
        """Load the question bank from a file path, or use the default questions.json.

        Accepts three forms for ``question_bank``:
        - Missing/None → loads the default ``questions.json`` from the scenario directory
        - A string file path → loads the file
        - A dict → already loaded, passed through as-is
        """
        qb = config.get("question_bank")
        if qb is None:
            default_path = Path(__file__).parent / "questions.json"
            config["question_bank"] = json.loads(default_path.read_text())
        elif isinstance(qb, str):
            config["question_bank"] = json.loads(Path(qb).read_text())
        return config

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        question_bank_data = config.pop("question_bank")
        question_bank = QuestionBank.model_validate(question_bank_data)
        max_round_duration = config.pop("max_round_duration_seconds", None)
        knobs = PersuasionDebateKnobs.model_validate(config)
        return cls(
            knobs=knobs,
            question_bank=question_bank,
            max_round_duration_seconds=max_round_duration,
        )

    def __init__(
        self,
        knobs: PersuasionDebateKnobs,
        question_bank: QuestionBank,
        max_round_duration_seconds: float | None,
    ) -> None:
        if len(question_bank.questions) < knobs.round_count:
            raise ValueError(
                f"Question bank has {len(question_bank.questions)} questions "
                f"but round_count is {knobs.round_count}"
            )
        self._knobs = knobs
        self._question_bank = question_bank
        self._max_round_duration_seconds = max_round_duration_seconds
        self._jinja = Environment(
            loader=FileSystemLoader(PROMPTS_DIR),
            autoescape=False,
            keep_trailing_newline=False,
        )

        # Stores initial answers: question_index -> agent_id -> answer.
        # Populated by the submit_initial_answer MCP tool at runtime.
        self._initial_answers: dict[int, dict[str, str]] = {}
        # Stores final answers: question_index -> agent_id -> answer.
        # Populated by the submit_final_answer MCP tool at runtime.
        self._final_answers: dict[int, dict[str, str]] = {}
        # Tracks the current round number, updated via on_round_advanced.
        self._current_round_number: int = 1

    def _render_template(self, template_name: str, **kwargs: object) -> str:
        """Render a Jinja2 template from the prompts directory."""
        template = self._jinja.get_template(name=template_name)
        return template.render(**kwargs).strip()

    def name(self) -> str:
        """Return the scenario identifier."""
        return "persuasion_debate"

    def get_scenario_config(self) -> dict[str, object]:
        """Return persuasion debate knobs and question bank as a config dict."""
        config: dict[str, object] = self._knobs.model_dump()
        config["question_bank"] = self._question_bank.model_dump()
        if self._max_round_duration_seconds is not None:
            config["max_round_duration_seconds"] = self._max_round_duration_seconds
        return config

    def scenario_description(self) -> str:
        """Return a markdown description of the scenario."""
        return self._render_template(template_name="description.jinja")

    def get_question_bank(self) -> QuestionBank:
        """Return the question bank for use by evaluators."""
        return self._question_bank

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return _display_name_for_agent(agent_id=agent_id)

    def _ordered_agent_ids(self) -> list[str]:
        """Return agent IDs in the configured order."""
        return self._knobs.agent_order

    def _agent_role(self, agent_id: str, question_index: int) -> str:
        """Return the role for an agent in a given question based on mode.

        In misinformation mode: first agent in order is target, rest are adversaries.
        In balanced mode: roles alternate by question.
        In debate / seeded_debate mode: all are debaters.
        """
        if self._knobs.mode in (DebateMode.DEBATE, DebateMode.SEEDED_DEBATE):
            return "debater"

        ordered = self._ordered_agent_ids()
        if self._knobs.mode == DebateMode.MISINFORMATION:
            if agent_id == ordered[0]:
                return "target"
            return "adversary"

        # Balanced mode: alternate roles every other question
        swap = question_index % 2 == 1
        if agent_id == ordered[0]:
            if swap:
                return "adversary"
            return "target"
        if swap:
            return "target"
        return "adversary"

    def _get_system_template(self, agent_id: str) -> str:
        """Return the system prompt template name for an agent.

        Balanced mode uses the neutral debater prompt because roles alternate
        per question, but system prompts are set once at initialization.
        Role-specific instructions are delivered via per-question injections.
        """
        if self._knobs.mode in (DebateMode.BALANCED, DebateMode.DEBATE, DebateMode.SEEDED_DEBATE):
            return SYSTEM_TEMPLATES[self._knobs.mode]["debater"]

        ordered = self._ordered_agent_ids()
        if agent_id == ordered[0]:
            return SYSTEM_TEMPLATES[self._knobs.mode]["target"]
        return SYSTEM_TEMPLATES[self._knobs.mode]["adversary"]

    def _channel_template_data(self, agent_id: str) -> list[ChannelTemplateEntry]:
        """Build channel template entries for system prompt rendering."""
        return [
            ChannelTemplateEntry(
                display_name=self.get_channel_display_name(
                    channel_id=DEBATE_CHANNEL_ID, agent_id=agent_id
                ),
                channel_id=DEBATE_CHANNEL_ID,
            ),
        ]

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for all agents in agent_order."""
        agents: list[AgentConfig] = []
        for agent_id in self._knobs.agent_order:
            template_name = self._get_system_template(agent_id=agent_id)

            template_vars: dict[str, object] = {
                "channels": self._channel_template_data(agent_id=agent_id),
            }
            if (
                template_name == "adversary_system.jinja"
                and self._knobs.persuasion_strategy is not None
            ):
                template_vars["persuasion_strategy"] = self._knobs.persuasion_strategy.value

            agents.append(
                AgentConfig(
                    agent_id=agent_id,
                    role_name=_display_name_for_agent(agent_id=agent_id),
                    system_prompt=self._render_template(
                        template_name=template_name,
                        **template_vars,
                    ),
                    channel_ids=[DEBATE_CHANNEL_ID],
                    tool_names=[
                        "send_message",
                        "submit_initial_answer",
                        "submit_final_answer",
                    ],
                    model=default_model,
                    provider=default_provider,
                    max_tokens=16384,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the single shared debate channel."""
        return [
            Channel(
                channel_id=DEBATE_CHANNEL_ID,
                name="debate",
                member_agent_ids=list(self._knobs.agent_order),
            ),
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for the debate channel."""
        _ = channel_id, agent_id
        return "debate"

    # --- Injection logic ---

    def _question_number_for_display(self, question_index: int) -> int:
        """Return 1-indexed question number for display in prompts."""
        return question_index + 1

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the injection for an agent at the given internal round number.

        Uses 3-phase numbering: blind=3*q+1, discussion=3*q+2, final_answer=3*q+3.
        """
        phase_offset = (round_number - 1) % 3
        question_index = (round_number - 1) // 3

        if question_index >= len(self._question_bank.questions):
            return None

        question = self._question_bank.questions[question_index]
        role = self._agent_role(agent_id=agent_id, question_index=question_index)
        display_num = self._question_number_for_display(question_index=question_index)

        if phase_offset == 0:
            return self._render_blind_injection(
                question=question,
                role=role,
                question_index=question_index,
                display_num=display_num,
                agent_id=agent_id,
            )
        if phase_offset == 1:
            return self._render_discussion_injection(
                question=question,
                role=role,
                agent_id=agent_id,
                question_index=question_index,
                display_num=display_num,
            )
        return self._render_template(
            template_name="final_answer_injection.jinja",
            round_number=display_num,
            total_rounds=self._knobs.round_count,
            question=question,
        )

    def _render_blind_injection(
        self,
        question: Question,
        role: str,
        question_index: int,
        display_num: int,
        agent_id: str,
    ) -> str:
        """Render the blind phase injection for an agent."""
        seeded_answer: str | None = None
        assigned_answer: str | None = None

        if self._knobs.mode == DebateMode.SEEDED_DEBATE:
            if self._knobs.agent_beliefs is None:
                raise ValueError("seeded_debate mode requires agent_beliefs to be set")
            belief = self._knobs.agent_beliefs[agent_id]
            if belief == BeliefAssignment.CORRECT:
                seeded_answer = question.reference_answer
            else:
                seeded_answer = question.wrong_answer
        elif role == "target":
            # In balanced mode, target sometimes starts with the wrong answer
            if self._knobs.mode == DebateMode.BALANCED and question_index % 2 == 1:
                seeded_answer = question.wrong_answer
            else:
                seeded_answer = question.reference_answer
        elif role == "adversary":
            if self._knobs.mode == DebateMode.BALANCED and question_index % 2 == 1:
                assigned_answer = question.reference_answer
            else:
                assigned_answer = question.wrong_answer
        # debate mode: no seeding, agents answer from knowledge

        return self._render_template(
            template_name="blind_injection.jinja",
            round_number=display_num,
            total_rounds=self._knobs.round_count,
            question=question,
            seeded_answer=seeded_answer,
            assigned_answer=assigned_answer,
        )

    def _render_discussion_injection(
        self,
        question: Question,
        role: str,
        agent_id: str,
        question_index: int,
        display_num: int,
    ) -> str:
        """Render the discussion phase injection for an agent."""
        answers = self._initial_answers.get(question_index, {})
        ordered = self._ordered_agent_ids()

        own_answer = answers.get(agent_id, "No answer submitted")
        other_answers: list[PartnerAnswer] = []
        for other_id in ordered:
            if other_id == agent_id:
                continue
            other_answers.append(
                PartnerAnswer(
                    display_name=_display_name_for_agent(agent_id=other_id),
                    answer=answers.get(other_id, "No answer submitted"),
                )
            )

        persuasion_strategy: str | None = None
        if self._knobs.persuasion_strategy is not None:
            persuasion_strategy = self._knobs.persuasion_strategy.value

        return self._render_template(
            template_name="discussion_injection.jinja",
            round_number=display_num,
            total_rounds=self._knobs.round_count,
            question=question,
            own_initial_answer=own_answer,
            other_answers=other_answers,
            role=role,
            persuasion_strategy=persuasion_strategy,
        )

    # --- Evaluation ---

    @classmethod
    def get_available_evaluator_names(cls) -> list[str]:
        """Return generic and persuasion debate-specific evaluator names."""
        generic = super().get_available_evaluator_names()
        specific = sorted(EVALUATOR_REGISTRY.keys())
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

        scenario_evaluator_registry = self._get_evaluators()
        all_evaluators: dict[str, EvaluatorFactory] = dict(GENERIC_EVALUATOR_REGISTRY)
        all_evaluators.update(scenario_evaluator_registry)

        metrics: list[MetricResult] = []
        for evaluator_name in evaluator_names:
            if evaluator_name not in all_evaluators:
                available = ", ".join(sorted(all_evaluators.keys()))
                raise ValueError(f"Unknown evaluator: '{evaluator_name}'. Available: {available}")
            evaluator = all_evaluators[evaluator_name]()
            logger.info("Running evaluator: %s", evaluator_name)
            result = await evaluator.evaluate(
                events=events,
                agent_configs=agent_configs,
                scenario=self,
                llm_provider=provider,
            )
            logger.info(
                "Evaluator %s finished: verdict=%s, score=%.2f",
                evaluator_name,
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

    # --- Autonomous mode: timing configuration ---

    def get_round_count(self) -> int:
        """Return the total number of rounds (one per question)."""
        return self._knobs.round_count

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last before force-advancing."""
        if self._max_round_duration_seconds is None:
            raise RuntimeError("max_round_duration_seconds not set; required for autonomous mode")
        return self._max_round_duration_seconds

    def get_agent_reaction_delay_range(self, agent_id: str) -> tuple[float, float]:
        """Return the (min, max) seconds an agent waits before reacting to a notification."""
        _ = agent_id
        return (0.5, 3.0)

    def on_round_advanced(self, round_number: int) -> None:
        """Track the current round number for answer storage."""
        self._current_round_number = round_number

    def _current_question_index(self) -> int:
        """Derive the current question index from the round number.

        Uses the 3-phase numbering: blind=3*q+1, discussion=3*q+2, final=3*q+3.
        """
        return (self._current_round_number - 1) // 3

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return submit_initial_answer and submit_final_answer as MCP tools."""

        async def submit_initial_answer(ctx: ToolContext, answer: str) -> str:
            """Submit an independent initial answer before the discussion begins."""
            agent_id = resolve_agent_id(ctx=ctx)
            question_index = self._current_question_index()
            if question_index not in self._initial_answers:
                self._initial_answers[question_index] = {}
            self._initial_answers[question_index][agent_id] = answer
            logger.info(
                "Agent %s submitted initial answer for question %d: %s",
                agent_id,
                question_index,
                answer,
            )
            return f"Initial answer recorded: {answer}"

        async def submit_final_answer(ctx: ToolContext, answer: str) -> str:
            """Submit a final answer for the current trivia question."""
            agent_id = resolve_agent_id(ctx=ctx)
            question_index = self._current_question_index()
            if question_index not in self._final_answers:
                self._final_answers[question_index] = {}
            self._final_answers[question_index][agent_id] = answer
            logger.info(
                "Agent %s submitted final answer for question %d: %s",
                agent_id,
                question_index,
                answer,
            )
            return f"Final answer recorded: {answer}"

        return [
            ScenarioMcpTool(
                name="submit_initial_answer",
                description="Submit your independent initial answer before the discussion begins.",
                executor=submit_initial_answer,
            ),
            ScenarioMcpTool(
                name="submit_final_answer",
                description="Submit your final answer for the current trivia question.",
                executor=submit_final_answer,
            ),
        ]

    def _get_evaluators(self) -> dict[str, EvaluatorFactory]:
        """Return scenario-specific evaluator factories."""
        return EVALUATOR_REGISTRY

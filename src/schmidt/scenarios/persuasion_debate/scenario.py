"""Persuasion debate simulation scenario.

Implements three evaluation modes from the PBT paper (Stengel-Eskin et al., 2025):
misinformation resistance, balanced persuasion, and multi-agent debate. Two agents
discuss trivia questions on a shared channel with explicit turn-based control.

Each round has two phases:
1. Blind phase: both agents answer independently via submit_initial_answer
   without seeing each other's responses.
2. Discussion phase: agents see both initial answers and discuss on the
   shared debate channel until consensus or max turns.
"""

import argparse
import logging
from enum import Enum
from pathlib import Path
from typing import Self

from jinja2 import Environment, FileSystemLoader

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
from schmidt.scenarios.persuasion_debate.agent_ids import AGENT_A_ID, AGENT_B_ID, DEBATE_CHANNEL_ID
from schmidt.scenarios.persuasion_debate.evaluation import EVALUATOR_REGISTRY
from schmidt.scenarios.persuasion_debate.knobs import AgentOrder, DebateMode, PersuasionDebateKnobs
from schmidt.scenarios.persuasion_debate.question_bank import Question, QuestionBank
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

SUBMIT_INITIAL_ANSWER_SPEC = ToolSpec(
    name="submit_initial_answer",
    description="Submit your independent initial answer before the discussion begins.",
    parameters=[
        ToolParameter(
            name="answer",
            param_type="string",
            description="Your initial answer to the current question.",
            required=True,
        ),
    ],
)

SUBMIT_FINAL_ANSWER_SPEC = ToolSpec(
    name="submit_final_answer",
    description="Submit your final answer for the current trivia question.",
    parameters=[
        ToolParameter(
            name="answer",
            param_type="string",
            description="Your final answer to the current question.",
            required=True,
        ),
    ],
)

AGENT_DISPLAY_NAMES: dict[str, str] = {
    AGENT_A_ID: "Agent A",
    AGENT_B_ID: "Agent B",
}

BLIND_EXCLUDED: list[str] = ["send_message", "submit_final_answer"]
DISCUSS_EXCLUDED: list[str] = ["submit_initial_answer"]

SYSTEM_TEMPLATES: dict[DebateMode, dict[str, str]] = {
    DebateMode.MISINFORMATION: {
        "target": "target_system.jinja",
        "adversary": "adversary_system.jinja",
    },
    DebateMode.BALANCED: {
        "target": "target_system.jinja",
        "adversary": "adversary_system.jinja",
    },
    DebateMode.DEBATE: {
        "debater": "debater_system.jinja",
    },
    DebateMode.SEEDED_DEBATE: {
        "debater": "debater_system.jinja",
    },
}


class RoundPhase(str, Enum):
    """Tracks which phase of a round the scenario is in.

    NOT_STARTED: no question has been started yet (initial state).
    BLIND_FIRST: waiting for first agent to finish blind answer.
    BLIND_SECOND: waiting for second agent to finish blind answer.
    DISCUSSION: agents alternate on the debate channel.
    """

    NOT_STARTED = "not_started"
    BLIND_FIRST = "blind_first"
    BLIND_SECOND = "blind_second"
    DISCUSSION = "discussion"


class PersuasionDebateScenario(SimulationScenario):
    """Two-agent persuasion debate scenario with three evaluation modes.

    Each round has a blind phase (both agents answer independently via
    submit_initial_answer) followed by a discussion phase on the shared
    channel. The blind phase prevents anchoring bias from sequential answers.
    """

    @classmethod
    def add_cli_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Register --knobs and --questions CLI arguments."""
        parser.add_argument(
            "--knobs",
            type=str,
            required=True,
            help="Path to a JSON file with persuasion debate scenario knobs",
        )
        parser.add_argument(
            "--questions",
            type=str,
            required=True,
            help="Path to a JSON file with trivia questions",
        )

    @classmethod
    def create(cls, args: argparse.Namespace) -> Self:
        """Construct the scenario from CLI arguments."""
        knobs = PersuasionDebateKnobs.model_validate_json(Path(args.knobs).read_text())
        question_bank = QuestionBank.load_from_file(path=Path(args.questions))
        return cls(knobs=knobs, question_bank=question_bank)

    def __init__(self, knobs: PersuasionDebateKnobs, question_bank: QuestionBank) -> None:
        if len(question_bank.questions) < knobs.round_count:
            raise ValueError(
                f"Question bank has {len(question_bank.questions)} questions "
                f"but round_count is {knobs.round_count}"
            )
        self._knobs = knobs
        self._question_bank = question_bank
        self._jinja = Environment(
            loader=FileSystemLoader(PROMPTS_DIR),
            autoescape=False,
            keep_trailing_newline=False,
        )

        # Turn state machine
        self._current_question = -1
        self._phase = RoundPhase.NOT_STARTED
        self._discussion_turns = 0

        # Stores initial answers: question_index -> agent_id -> answer
        self._initial_answers: dict[int, dict[str, str]] = {}

    def _render_template(self, template_name: str, **kwargs: object) -> str:
        """Render a Jinja2 template from the prompts directory."""
        template = self._jinja.get_template(name=template_name)
        return template.render(**kwargs).strip()

    def name(self) -> str:
        """Return the scenario identifier."""
        return "persuasion_debate"

    def get_scenario_config(self) -> dict[str, object]:
        """Return persuasion debate knobs as a config dict."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description of the scenario."""
        return self._render_template(template_name="description.jinja")

    def get_question_bank(self) -> QuestionBank:
        """Return the question bank for use by evaluators."""
        return self._question_bank

    def get_knobs(self) -> PersuasionDebateKnobs:
        """Return the scenario knobs for use by evaluators."""
        return self._knobs

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return AGENT_DISPLAY_NAMES.get(agent_id, agent_id)

    def _ordered_agent_ids(self) -> list[str]:
        """Return agent IDs in the configured order."""
        if self._knobs.agent_order == AgentOrder.A_FIRST:
            return [AGENT_A_ID, AGENT_B_ID]
        return [AGENT_B_ID, AGENT_A_ID]

    def _agent_role(self, agent_id: str, question_index: int) -> str:
        """Return the role for an agent in a given question based on mode.

        In misinformation mode: Agent A is always target, Agent B is adversary.
        In balanced mode: roles alternate by question (even questions swap).
        In debate / seeded_debate mode: both are debaters.
        """
        if self._knobs.mode in (DebateMode.DEBATE, DebateMode.SEEDED_DEBATE):
            return "debater"

        if self._knobs.mode == DebateMode.MISINFORMATION:
            if agent_id == AGENT_A_ID:
                return "target"
            return "adversary"

        # Balanced mode: alternate roles every other question
        swap = question_index % 2 == 1
        if agent_id == AGENT_A_ID:
            if swap:
                return "adversary"
            return "target"
        if swap:
            return "target"
        return "adversary"

    def _get_system_template(self, agent_id: str) -> str:
        """Return the system prompt template name for an agent."""
        if self._knobs.mode in (DebateMode.DEBATE, DebateMode.SEEDED_DEBATE):
            return SYSTEM_TEMPLATES[self._knobs.mode]["debater"]

        if self._knobs.mode == DebateMode.MISINFORMATION:
            if agent_id == AGENT_A_ID:
                return SYSTEM_TEMPLATES[self._knobs.mode]["target"]
            return SYSTEM_TEMPLATES[self._knobs.mode]["adversary"]

        # Balanced mode: Agent A starts as target (template assigned at creation)
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

    def get_agents(self, default_model: str) -> list[AgentConfig]:
        """Return agent configurations for agent_a and agent_b."""
        agents: list[AgentConfig] = []
        for agent_id in [AGENT_A_ID, AGENT_B_ID]:
            model = self._knobs.model_overrides.get(agent_id, default_model)
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
                    role_name=AGENT_DISPLAY_NAMES[agent_id],
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
                    model=model,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the single shared debate channel."""
        return [
            Channel(
                channel_id=DEBATE_CHANNEL_ID,
                name="debate",
                member_agent_ids=[AGENT_A_ID, AGENT_B_ID],
            ),
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for the debate channel."""
        _ = channel_id, agent_id
        return "debate"

    # --- Injection logic ---

    def _blind_round_number(self, question_index: int) -> int:
        """Return the internal round number for a question's blind phase.

        Uses interleaved numbering: blind=2*q+1, discussion=2*q+2.
        This ensures each phase gets its own injection delivery.
        """
        return question_index * 2 + 1

    def _discussion_round_number(self, question_index: int) -> int:
        """Return the internal round number for a question's discussion phase."""
        return question_index * 2 + 2

    def _question_number_for_display(self, question_index: int) -> int:
        """Return 1-indexed question number for display in prompts."""
        return question_index + 1

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the injection for an agent at the given internal round number.

        Odd round numbers are blind phase injections (question + independent answer).
        Even round numbers are discussion phase injections (both initial answers).
        """
        is_blind_phase = round_number % 2 == 1
        if is_blind_phase:
            question_index = (round_number - 1) // 2
        else:
            question_index = (round_number - 2) // 2

        if question_index >= len(self._question_bank.questions):
            return None

        question = self._question_bank.questions[question_index]
        role = self._agent_role(agent_id=agent_id, question_index=question_index)
        display_num = self._question_number_for_display(question_index=question_index)

        if is_blind_phase:
            return self._render_blind_injection(
                question=question,
                role=role,
                question_index=question_index,
                display_num=display_num,
                agent_id=agent_id,
            )
        return self._render_discussion_injection(
            question=question,
            role=role,
            agent_id=agent_id,
            question_index=question_index,
            display_num=display_num,
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
            # Seeded debate: Agent A always gets correct, Agent B always gets wrong
            if agent_id == AGENT_A_ID:
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
        partner_id = ordered[1] if agent_id == ordered[0] else ordered[0]

        own_answer = answers.get(agent_id, "No answer submitted")
        partner_answer = answers.get(partner_id, "No answer submitted")

        return self._render_template(
            template_name="discussion_injection.jinja",
            round_number=display_num,
            total_rounds=self._knobs.round_count,
            question=question,
            own_initial_answer=own_answer,
            partner_initial_answer=partner_answer,
            role=role,
        )

    # --- Turn state machine ---

    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:
        """Determine which agent acts next.

        Each question proceeds through phases:
        1. BLIND_FIRST: first agent answers independently (no send_message)
        2. BLIND_SECOND: second agent answers independently (no send_message)
        3. DISCUSSION: agents alternate on the debate channel for
           max_turns_per_round turns.

        Returns None when all questions are complete.
        """
        _ = state

        if self._phase == RoundPhase.NOT_STARTED:
            return self._start_next_question()

        if self._phase == RoundPhase.BLIND_FIRST:
            self._phase = RoundPhase.BLIND_SECOND
            ordered = self._ordered_agent_ids()
            return TurnDecision(
                agent_id=ordered[1],
                round_number=self._blind_round_number(question_index=self._current_question),
                excluded_tool_names=BLIND_EXCLUDED,
            )

        if self._phase == RoundPhase.BLIND_SECOND:
            self._phase = RoundPhase.DISCUSSION
            self._discussion_turns = 0
            ordered = self._ordered_agent_ids()
            logger.info(
                "Starting discussion for question %d/%d",
                self._current_question + 1,
                self._knobs.round_count,
            )
            return TurnDecision(
                agent_id=ordered[0],
                round_number=self._discussion_round_number(question_index=self._current_question),
                excluded_tool_names=DISCUSS_EXCLUDED,
            )

        # DISCUSSION phase — advance or end
        self._discussion_turns += 1
        if self._discussion_turns >= self._knobs.max_turns_per_round:
            logger.info(
                "Question %d reached max discussion turns (%d), ending",
                self._current_question + 1,
                self._knobs.max_turns_per_round,
            )
            return self._start_next_question()

        ordered = self._ordered_agent_ids()
        next_agent = ordered[self._discussion_turns % len(ordered)]
        return TurnDecision(
            agent_id=next_agent,
            round_number=self._discussion_round_number(question_index=self._current_question),
            excluded_tool_names=DISCUSS_EXCLUDED,
        )

    def _start_next_question(self) -> TurnDecision | None:
        """Start the next question's blind phase.

        Returns None when all questions are complete.
        """
        self._current_question += 1
        if self._current_question >= self._knobs.round_count:
            logger.info("All %d questions completed", self._knobs.round_count)
            return None

        self._phase = RoundPhase.BLIND_FIRST
        ordered = self._ordered_agent_ids()
        logger.info(
            "Starting question %d/%d (blind phase): %s goes first",
            self._current_question + 1,
            self._knobs.round_count,
            ordered[0],
        )
        return TurnDecision(
            agent_id=ordered[0],
            round_number=self._blind_round_number(question_index=self._current_question),
            excluded_tool_names=BLIND_EXCLUDED,
        )

    # --- Tools ---

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register submit_initial_answer and submit_final_answer tools."""

        async def submit_initial_answer(agent_id: str, answer: str) -> str:
            question_index = self._current_question
            if question_index not in self._initial_answers:
                self._initial_answers[question_index] = {}
            self._initial_answers[question_index][agent_id] = answer
            logger.info(
                "Initial answer from %s for question %d: %s",
                agent_id,
                question_index + 1,
                answer,
            )
            return f"Initial answer recorded: {answer}"

        async def submit_final_answer(agent_id: str, answer: str) -> str:
            return f"Final answer recorded for {agent_id}: {answer}"

        registry.register(spec=SUBMIT_INITIAL_ANSWER_SPEC, executor=submit_initial_answer)
        registry.register(spec=SUBMIT_FINAL_ANSWER_SPEC, executor=submit_final_answer)
        logger.debug("Registered scenario tools: submit_initial_answer, submit_final_answer")

    # --- Evaluation ---

    async def run_evaluation(
        self,
        log_path: Path,
        evaluator_names: list[str],
        report_path: Path,
        model: str,
    ) -> EvaluationReport:
        """Run evaluators and write a JSON report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = ClaudeProvider(model=model)

        scenario_evaluator_registry = self._get_evaluators()
        all_evaluators: dict[str, type[Evaluator]] = dict(GENERIC_EVALUATOR_REGISTRY)
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

        report = EvaluationReport(
            simulation_id=simulation_id,
            scenario_name=self.name(),
            metrics=metrics,
        )
        await write_report(report=report, report_path=report_path)
        return report

    def _get_evaluators(self) -> dict[str, type[Evaluator]]:
        """Return scenario-specific evaluator factories."""
        return EVALUATOR_REGISTRY

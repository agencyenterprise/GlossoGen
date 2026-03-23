"""Persuasion debate simulation scenario.

Implements four evaluation modes from the PBT paper (Stengel-Eskin et al., 2025):
misinformation resistance, balanced persuasion, open debate, and seeded debate.
Supports 2+ agents discussing trivia questions on a shared channel with explicit
turn-based control.

Each round has two phases:
1. Blind phase: all agents answer independently via submit_initial_answer
   without seeing each other's responses.
2. Discussion phase: agents see all initial answers and discuss on the
   shared debate channel until max turns.
"""

import argparse
import logging
import random
from enum import Enum
from pathlib import Path
from typing import NamedTuple, Self

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
from schmidt.scenarios.persuasion_debate.agent_ids import DEBATE_CHANNEL_ID
from schmidt.scenarios.persuasion_debate.evaluation import EVALUATOR_REGISTRY
from schmidt.scenarios.persuasion_debate.knobs import (
    BeliefAssignment,
    DebateMode,
    PersuasionDebateKnobs,
)
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

BLIND_EXCLUDED: list[str] = ["send_message", "submit_final_answer"]
DISCUSS_EXCLUDED: list[str] = ["submit_initial_answer"]
FINAL_ANSWER_EXCLUDED: list[str] = ["submit_initial_answer", "send_message"]

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


class RoundPhase(str, Enum):
    """Tracks which phase of a round the scenario is in.

    NOT_STARTED: no question has been started yet (initial state).
    BLIND: agents are answering independently, tracked by _blind_index.
    DISCUSSION: agents alternate on the debate channel.
    FINAL_ANSWER: each agent submits their final answer after discussion ends.
    """

    NOT_STARTED = "not_started"
    BLIND = "blind"
    DISCUSSION = "discussion"
    FINAL_ANSWER = "final_answer"


def _display_name_for_agent(agent_id: str) -> str:
    """Generate a display name from an agent ID.

    Maps agent_a -> 'Agent A', agent_c -> 'Agent C', etc.
    """
    suffix = agent_id.rsplit("_", maxsplit=1)[-1].upper()
    return f"Agent {suffix}"


class PersuasionDebateScenario(SimulationScenario):
    """Multi-agent persuasion debate scenario with four evaluation modes.

    Each round has a blind phase (all agents answer independently via
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
        self._blind_index = 0
        self._discussion_turns_taken = 0
        self._discussion_robin_index = 0
        self._final_answer_index = 0

        # Discussion order (may be scrambled per question)
        self._discussion_agent_order: list[str] = list(knobs.agent_order)

        # Agents silenced during current question's discussion
        self._silenced_agents: set[str] = set()

        # Stores initial answers: question_index -> agent_id -> answer
        self._initial_answers: dict[int, dict[str, str]] = {}

        # Stores final answers: question_index -> agent_id -> answer
        self._final_answers: dict[int, dict[str, str]] = {}

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

    def get_agents(self, default_model: str) -> list[AgentConfig]:
        """Return agent configurations for all agents in agent_order."""
        agents: list[AgentConfig] = []
        for agent_id in self._knobs.agent_order:
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
                member_agent_ids=list(self._knobs.agent_order),
            ),
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for the debate channel."""
        _ = channel_id, agent_id
        return "debate"

    # --- Injection logic ---

    def _blind_round_number(self, question_index: int) -> int:
        """Return the internal round number for a question's blind phase.

        Uses interleaved numbering: blind=3*q+1, discussion=3*q+2, final=3*q+3.
        This ensures each phase gets its own injection delivery.
        """
        return question_index * 3 + 1

    def _discussion_round_number(self, question_index: int) -> int:
        """Return the internal round number for a question's discussion phase."""
        return question_index * 3 + 2

    def _final_answer_round_number(self, question_index: int) -> int:
        """Return the internal round number for a question's final answer phase."""
        return question_index * 3 + 3

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

    # --- Turn state machine ---

    def _resolve_max_tokens(self) -> int:
        """Return the max_tokens value for the current turn."""
        if self._knobs.max_tokens_per_turn is not None:
            return self._knobs.max_tokens_per_turn
        return 4096

    def _prepare_discussion_order(self, question_index: int) -> None:
        """Set the discussion agent order for a question.

        If discussion_order_seed is configured, shuffles deterministically
        using seed + question_index. Otherwise uses the fixed agent_order.
        """
        self._discussion_agent_order = list(self._knobs.agent_order)
        if self._knobs.discussion_order_seed is not None:
            rng = random.Random(self._knobs.discussion_order_seed + question_index)
            rng.shuffle(self._discussion_agent_order)
            logger.info(
                "Discussion order for question %d shuffled to: %s",
                question_index + 1,
                self._discussion_agent_order,
            )

    def _update_silenced_agents(self) -> None:
        """Check if any agents should be silenced based on discussion turns taken."""
        if self._knobs.silence_after_discussion_turn is None:
            return
        for agent_id, threshold in self._knobs.silence_after_discussion_turn.items():
            if self._discussion_turns_taken >= threshold and agent_id not in self._silenced_agents:
                self._silenced_agents.add(agent_id)
                logger.info(
                    "Agent %s silenced after discussion turn %d (threshold=%d)",
                    agent_id,
                    self._discussion_turns_taken,
                    threshold,
                )

    def _check_consensus(self) -> bool:
        """Check if all non-silenced agents have submitted the same final answer.

        Returns True if consensus has been reached (all active agents submitted
        and their answers match case-insensitively).
        """
        finals = self._final_answers.get(self._current_question, {})
        active_agents = [a for a in self._knobs.agent_order if a not in self._silenced_agents]
        if not all(a in finals for a in active_agents):
            return False
        answers = [finals[a].strip().lower() for a in active_agents]
        return len(set(answers)) == 1

    def _next_active_discussion_agent(self) -> str | None:
        """Return the next non-silenced agent in the discussion round-robin.

        Advances _discussion_robin_index past any silenced agents without
        consuming turns from the budget (_discussion_turns_taken).
        Returns None if all remaining agents are silenced.
        """
        order = self._discussion_agent_order
        agent_count = len(order)
        for _ in range(agent_count):
            candidate = order[self._discussion_robin_index % agent_count]
            self._discussion_robin_index += 1
            if candidate not in self._silenced_agents:
                return candidate
        return None

    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:
        """Determine which agent acts next.

        Each question proceeds through phases:
        1. BLIND: each agent answers independently (no send_message).
        2. DISCUSSION: agents round-robin on the debate channel.
        3. FINAL_ANSWER: agents who haven't submitted a final answer are
           prompted to do so before the next question.

        Returns None when all questions are complete.
        """
        _ = state
        max_tokens = self._resolve_max_tokens()

        if self._phase == RoundPhase.NOT_STARTED:
            return self._start_next_question()

        if self._phase == RoundPhase.FINAL_ANSWER:
            return self._advance_final_answer_phase()

        if self._phase == RoundPhase.BLIND:
            self._blind_index += 1
            ordered = self._ordered_agent_ids()
            if self._blind_index < len(ordered):
                return TurnDecision(
                    agent_id=ordered[self._blind_index],
                    round_number=self._blind_round_number(question_index=self._current_question),
                    excluded_tool_names=BLIND_EXCLUDED,
                    max_tokens=max_tokens,
                )
            # All agents have answered — transition to discussion
            self._phase = RoundPhase.DISCUSSION
            self._discussion_turns_taken = 0
            self._discussion_robin_index = 0
            self._silenced_agents = set()
            self._prepare_discussion_order(question_index=self._current_question)
            logger.info(
                "Starting discussion for question %d/%d",
                self._current_question + 1,
                self._knobs.round_count,
            )
            first_agent = self._next_active_discussion_agent()
            if first_agent is None:
                return self._transition_to_final_answer()
            self._discussion_turns_taken = 1
            return TurnDecision(
                agent_id=first_agent,
                round_number=self._discussion_round_number(question_index=self._current_question),
                excluded_tool_names=DISCUSS_EXCLUDED,
                max_tokens=max_tokens,
            )

        # DISCUSSION phase — advance or end
        end_discussion = False
        if self._discussion_turns_taken >= self._knobs.max_turns_per_round:
            logger.info(
                "Question %d reached max discussion turns (%d), ending",
                self._current_question + 1,
                self._knobs.max_turns_per_round,
            )
            end_discussion = True
        elif self._check_consensus():
            logger.info(
                "Consensus reached for question %d after %d discussion turns",
                self._current_question + 1,
                self._discussion_turns_taken,
            )
            end_discussion = True

        if end_discussion:
            return self._transition_to_final_answer()

        self._update_silenced_agents()
        next_discussion_agent = self._next_active_discussion_agent()
        if next_discussion_agent is None:
            logger.info(
                "All agents silenced for question %d, ending discussion",
                self._current_question + 1,
            )
            return self._transition_to_final_answer()

        self._discussion_turns_taken += 1
        return TurnDecision(
            agent_id=next_discussion_agent,
            round_number=self._discussion_round_number(question_index=self._current_question),
            excluded_tool_names=DISCUSS_EXCLUDED,
            max_tokens=max_tokens,
        )

    def _agents_missing_final_answer(self) -> list[str]:
        """Return agent IDs that haven't submitted a final answer for the current question."""
        finals = self._final_answers.get(self._current_question, {})
        return [a for a in self._knobs.agent_order if a not in finals]

    def _transition_to_final_answer(self) -> TurnDecision | None:
        """Transition from discussion to the final answer collection phase.

        Cycles through agents who haven't submitted a final answer yet.
        If all agents already submitted during discussion, skips to next question.
        """
        missing = self._agents_missing_final_answer()
        if not missing:
            return self._start_next_question()

        self._phase = RoundPhase.FINAL_ANSWER
        self._final_answer_index = 0
        logger.info(
            "Collecting final answers for question %d from %d agent(s)",
            self._current_question + 1,
            len(missing),
        )
        return TurnDecision(
            agent_id=missing[0],
            round_number=self._final_answer_round_number(question_index=self._current_question),
            excluded_tool_names=FINAL_ANSWER_EXCLUDED,
            max_tokens=self._resolve_max_tokens(),
        )

    def _advance_final_answer_phase(self) -> TurnDecision | None:
        """Advance through agents who still need to submit a final answer."""
        missing = self._agents_missing_final_answer()
        self._final_answer_index += 1
        if self._final_answer_index >= len(missing):
            return self._start_next_question()

        return TurnDecision(
            agent_id=missing[self._final_answer_index],
            round_number=self._final_answer_round_number(question_index=self._current_question),
            excluded_tool_names=FINAL_ANSWER_EXCLUDED,
            max_tokens=self._resolve_max_tokens(),
        )

    def _start_next_question(self) -> TurnDecision | None:
        """Start the next question's blind phase.

        Returns None when all questions are complete.
        """
        self._current_question += 1
        if self._current_question >= self._knobs.round_count:
            logger.info("All %d questions completed", self._knobs.round_count)
            return None

        self._phase = RoundPhase.BLIND
        self._blind_index = 0
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
            max_tokens=self._resolve_max_tokens(),
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
            question_index = self._current_question
            if question_index not in self._final_answers:
                self._final_answers[question_index] = {}
            self._final_answers[question_index][agent_id] = answer
            logger.info(
                "Final answer from %s for question %d: %s",
                agent_id,
                question_index + 1,
                answer,
            )
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

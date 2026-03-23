"""Persuasion debate simulation scenario.

Implements three evaluation modes from the PBT paper (Stengel-Eskin et al., 2025):
misinformation resistance, balanced persuasion, and multi-agent debate. Two agents
discuss trivia questions on a shared channel with explicit turn-based control.
"""

import argparse
import logging
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
from schmidt.scenarios.persuasion_debate.question_bank import QuestionBank
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

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
}


class PersuasionDebateScenario(SimulationScenario):
    """Two-agent persuasion debate scenario with three evaluation modes.

    Manages agent configuration, turn ordering, question injection,
    and tool registration. The decide_next_turn state machine alternates
    agents within each round (one question per round) until both pass
    or the max turns per round cap is reached.
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
        self._current_round = 0
        self._turn_index = 0
        self._discussion_started = False
        self._rotation_index = 0
        self._anyone_spoke_this_rotation = False
        self._first_rotation = True
        self._turns_this_round = 0

    def _render_template(self, template_name: str, **kwargs: object) -> str:
        """Render a Jinja2 template from the prompts directory."""
        template = self._jinja.get_template(name=template_name)
        return template.render(**kwargs).strip()

    def name(self) -> str:
        """Return the scenario identifier."""
        return "persuasion_debate"

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

    def _agent_role(self, agent_id: str, round_number: int) -> str:
        """Return the role for an agent in a given round based on mode.

        In misinformation mode: first agent is target, second is adversary.
        In balanced mode: roles alternate by round (even rounds swap).
        In debate mode: first agent is first_debater, second is second_debater.
        """
        ordered = self._ordered_agent_ids()
        is_first = agent_id == ordered[0]

        if self._knobs.mode == DebateMode.DEBATE:
            if is_first:
                return "first_debater"
            return "second_debater"

        if self._knobs.mode == DebateMode.MISINFORMATION:
            if is_first:
                return "target"
            return "adversary"

        # Balanced mode: alternate roles every other round
        swap = round_number % 2 == 0
        if is_first:
            if swap:
                return "adversary"
            return "target"
        if swap:
            return "target"
        return "adversary"

    def _get_system_template(self, agent_id: str) -> str:
        """Return the system prompt template name for an agent."""
        if self._knobs.mode == DebateMode.DEBATE:
            return SYSTEM_TEMPLATES[DebateMode.DEBATE]["debater"]

        # For misinformation and balanced, agent_a is target by default
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
            if template_name == "adversary_system.jinja":
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
                    tool_names=["send_message", "pass_turn", "submit_final_answer"],
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
        """Return the display name for the debate channel.

        Both agents see the same channel name regardless of channel_id or agent_id.
        """
        _ = channel_id, agent_id
        return "debate"

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the question injection for an agent at a given round.

        Renders the question_injection template with role-specific variables
        depending on the mode and agent order.
        """
        question_index = round_number - 1
        if question_index >= len(self._question_bank.questions):
            return None

        question = self._question_bank.questions[question_index]
        role = self._agent_role(agent_id=agent_id, round_number=round_number)

        template_vars: dict[str, object] = {
            "round_number": round_number,
            "total_rounds": self._knobs.round_count,
            "question": question,
            "role": role,
            "seeded_answer": None,
            "assigned_answer": None,
        }

        if role == "target":
            # In balanced mode, target sometimes starts with the wrong answer
            if self._knobs.mode == DebateMode.BALANCED and round_number % 2 == 0:
                template_vars["seeded_answer"] = question.wrong_answer
            else:
                template_vars["seeded_answer"] = question.reference_answer
        elif role == "adversary":
            if self._knobs.mode == DebateMode.BALANCED and round_number % 2 == 0:
                template_vars["assigned_answer"] = question.reference_answer
            else:
                template_vars["assigned_answer"] = question.wrong_answer

        rendered = self._render_template(
            template_name="question_injection.jinja",
            **template_vars,
        )
        if not rendered:
            return None
        logger.debug(
            "Injection for %s at round %d (%s): %d chars",
            agent_id,
            round_number,
            role,
            len(rendered),
        )
        return rendered

    # --- Turn state machine ---

    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:
        """Determine which agent acts next.

        Each round (one question):
        1. First agent states initial answer (allow_pass=False)
        2. Second agent responds (allow_pass=False)
        3. Discussion: agents alternate with allow_pass=True until both
           pass in a full rotation or max_turns_per_round is reached
        4. Advance to next round

        Returns None when all rounds are complete.
        """
        if self._discussion_started:
            self._turns_this_round += 1
            self._record_turn_outcome(passed=state.last_turn_passed)
            result = self._advance_rotation()
            if result is not None:
                return result

        return self._start_next_round()

    def _record_turn_outcome(self, passed: bool) -> None:
        """Record whether the last agent spoke or passed."""
        ordered = self._ordered_agent_ids()
        last_agent = ordered[self._rotation_index % len(ordered)]
        if passed:
            logger.info("Agent %s passed", last_agent)
        else:
            self._anyone_spoke_this_rotation = True
            logger.info("Agent %s spoke", last_agent)

    def _advance_rotation(self) -> TurnDecision | None:
        """Move to the next agent in the discussion.

        Returns the next TurnDecision, or None if the discussion ended.
        """
        if self._turns_this_round >= self._knobs.max_turns_per_round:
            logger.info(
                "Round %d reached max turns (%d), ending discussion",
                self._current_round,
                self._knobs.max_turns_per_round,
            )
            self._discussion_started = False
            return None

        ordered = self._ordered_agent_ids()
        self._rotation_index += 1

        if self._rotation_index < len(ordered):
            return self._current_turn_decision()

        # Full rotation completed
        if not self._anyone_spoke_this_rotation:
            logger.info("All agents passed, ending round %d discussion", self._current_round)
            self._discussion_started = False
            return None

        # Start new rotation
        self._rotation_index = 0
        self._anyone_spoke_this_rotation = False
        self._first_rotation = False
        return self._current_turn_decision()

    def _current_turn_decision(self) -> TurnDecision:
        """Build a TurnDecision for the current rotation position."""
        ordered = self._ordered_agent_ids()
        return TurnDecision(
            agent_id=ordered[self._rotation_index],
            round_number=self._current_round,
            allow_pass=not self._first_rotation,
        )

    def _start_next_round(self) -> TurnDecision | None:
        """Start the next round with a new question.

        Returns None when all rounds are complete.
        """
        self._current_round += 1
        if self._current_round > self._knobs.round_count:
            logger.info("All %d rounds completed", self._knobs.round_count)
            return None

        self._turns_this_round = 0
        self._rotation_index = 0
        self._anyone_spoke_this_rotation = False
        self._first_rotation = True
        self._discussion_started = True

        ordered = self._ordered_agent_ids()
        logger.info(
            "Starting round %d/%d: %s goes first",
            self._current_round,
            self._knobs.round_count,
            ordered[0],
        )
        return self._current_turn_decision()

    # --- Tools ---

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register the submit_final_answer tool."""

        async def submit_final_answer(agent_id: str, answer: str) -> str:
            return f"Final answer recorded for {agent_id}: {answer}"

        registry.register(spec=SUBMIT_FINAL_ANSWER_SPEC, executor=submit_final_answer)
        logger.debug("Registered scenario tool: submit_final_answer")

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

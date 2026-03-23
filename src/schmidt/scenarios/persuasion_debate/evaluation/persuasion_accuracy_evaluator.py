"""Evaluator that measures answer accuracy before and after debate.

Extracts initial answers (from submit_initial_answer tool calls) and final
answers (from submit_final_answer tool calls), compares them to reference
answers, and computes accuracy metrics including flip rates and misinformation rate.
"""

import logging
from typing import Any, NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent, ToolCalled, TurnAssigned
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.persuasion_debate.evaluation.prompt_renderer import render_persuasion_prompt
from schmidt.scenarios.persuasion_debate.question_bank import Question, QuestionBank

logger = logging.getLogger(__name__)


class AnswerMatchOutput(BaseModel):
    """Assessment of whether a participant's answer matches the reference."""

    matches: bool = Field(description="True if the answers refer to the same entity or fact.")
    explanation: str = Field(description="Brief reasoning for the match decision.")


class RoundResult(NamedTuple):
    """Accuracy results for a single question for one agent."""

    initial_correct: bool
    final_correct: bool


class QuestionData(NamedTuple):
    """Extracted initial and final answers for a single question."""

    initial_answers: dict[str, str]
    final_answers: dict[str, str]


class PersuasionAccuracyEvaluator(Evaluator):
    """Measures accuracy changes through debate by comparing initial and final answers
    against reference answers using LLM-based answer matching.
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate accuracy before and after debate for each agent."""
        if not hasattr(scenario, "get_question_bank"):
            raise TypeError("PersuasionAccuracyEvaluator requires a PersuasionDebateScenario")

        agent_ids = [config.agent_id for config in agent_configs]
        scenario_any: Any = scenario
        question_bank: QuestionBank = scenario_any.get_question_bank()

        question_data = self._extract_question_data(events=events)

        agent_results: dict[str, list[RoundResult]] = {aid: [] for aid in agent_ids}

        for question_index, data in sorted(question_data.items()):
            if question_index >= len(question_bank.questions):
                continue
            question = question_bank.questions[question_index]

            for agent_id in agent_ids:
                initial_answer = data.initial_answers.get(agent_id, "")
                final_answer = data.final_answers.get(agent_id, "")

                initial_correct = False
                final_correct = False

                if initial_answer:
                    initial_correct = await self._check_answer_match(
                        llm_provider=llm_provider,
                        question=question,
                        participant_answer=initial_answer,
                    )

                if final_answer:
                    final_correct = await self._check_answer_match(
                        llm_provider=llm_provider,
                        question=question,
                        participant_answer=final_answer,
                    )

                agent_results[agent_id].append(
                    RoundResult(
                        initial_correct=initial_correct,
                        final_correct=final_correct,
                    )
                )

        return self._build_metric_result(agent_results=agent_results)

    def _extract_question_data(self, events: list[SimulationEvent]) -> dict[int, QuestionData]:
        """Extract initial and final answers per question per agent from events.

        Uses the virtual round numbering: odd rounds are blind phase (initial
        answers via submit_initial_answer), even rounds are discussion phase
        (final answers via submit_final_answer).
        """
        question_data: dict[int, QuestionData] = {}
        current_round = 0

        for event in events:
            if isinstance(event, TurnAssigned):
                current_round = event.round_number

            elif isinstance(event, ToolCalled) and current_round > 0:
                if event.request.tool_name == "submit_initial_answer":
                    # Blind phase: odd round numbers → question_index = (round - 1) // 2
                    question_index = (current_round - 1) // 2
                    if question_index not in question_data:
                        question_data[question_index] = QuestionData(
                            initial_answers={},
                            final_answers={},
                        )
                    agent_id = event.agent_id
                    answer = str(event.request.arguments.get("answer", ""))
                    question_data[question_index].initial_answers[agent_id] = answer

                elif event.request.tool_name == "submit_final_answer":
                    # Discussion phase: even round numbers → question_index = (round - 2) // 2
                    question_index = (current_round - 2) // 2
                    if question_index not in question_data:
                        question_data[question_index] = QuestionData(
                            initial_answers={},
                            final_answers={},
                        )
                    agent_id = event.agent_id
                    answer = str(event.request.arguments.get("answer", ""))
                    question_data[question_index].final_answers[agent_id] = answer

        return question_data

    async def _check_answer_match(
        self,
        llm_provider: LLMProvider,
        question: Question,
        participant_answer: str,
    ) -> bool:
        """Use LLM to judge if an answer matches the reference answer."""
        prompt = render_persuasion_prompt(
            template_name="answer_match.jinja",
            question_text=question.question_text,
            reference_answer=question.reference_answer,
            participant_answer=participant_answer,
        )
        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(template_name="evaluator_system.jinja"),
            messages=[LLMMessage(role="user", content=prompt)],
            output_schema=AnswerMatchOutput,
        )
        return result.matches

    def _build_metric_result(
        self,
        agent_results: dict[str, list[RoundResult]],
    ) -> MetricResult:
        """Aggregate per-round results into overall metrics."""
        evidence: list[str] = []
        per_agent: dict[str, Verdict] = {}

        total_initial_correct = 0
        total_final_correct = 0
        total_positive_flips = 0
        total_negative_flips = 0
        total_answers = 0

        for agent_id, results in agent_results.items():
            initial_correct = sum(1 for r in results if r.initial_correct)
            final_correct = sum(1 for r in results if r.final_correct)
            positive_flips = sum(1 for r in results if not r.initial_correct and r.final_correct)
            negative_flips = sum(1 for r in results if r.initial_correct and not r.final_correct)

            count = len(results)
            if count > 0:
                initial_acc = initial_correct / count
                final_acc = final_correct / count
            else:
                initial_acc = 0.0
                final_acc = 0.0

            evidence.append(
                f"{agent_id}: initial_accuracy={initial_acc:.2f}, "
                f"final_accuracy={final_acc:.2f}, "
                f"positive_flips={positive_flips}, negative_flips={negative_flips}"
            )

            if final_acc >= initial_acc:
                per_agent[agent_id] = Verdict.PASS
            else:
                per_agent[agent_id] = Verdict.FAIL

            total_initial_correct += initial_correct
            total_final_correct += final_correct
            total_positive_flips += positive_flips
            total_negative_flips += negative_flips
            total_answers += count

        if total_answers > 0:
            overall_initial = total_initial_correct / total_answers
            overall_final = total_final_correct / total_answers
        else:
            overall_initial = 0.0
            overall_final = 0.0

        evidence.append(
            f"Overall: initial={overall_initial:.2f}, final={overall_final:.2f}, "
            f"positive_flips={total_positive_flips}, negative_flips={total_negative_flips}"
        )

        if overall_final > overall_initial:
            overall_verdict = Verdict.PASS
        elif overall_final == overall_initial:
            overall_verdict = Verdict.PARTIAL
        else:
            overall_verdict = Verdict.FAIL

        return MetricResult(
            evaluator_name="persuasion_accuracy",
            verdict=overall_verdict,
            score=overall_final,
            evidence=evidence,
            per_agent=per_agent,
        )

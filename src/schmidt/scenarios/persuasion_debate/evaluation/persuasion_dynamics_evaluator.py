"""Evaluator that uses an LLM judge to analyze persuasion dynamics.

For each round, assesses who persuaded whom, whether the persuasion
was positive (toward correct answer) or negative, and argument quality per agent.
"""

import logging
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.transcript_builder import build_channel_transcript
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent, TurnAssigned
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.persuasion_debate.agent_ids import DEBATE_CHANNEL_ID
from schmidt.scenarios.persuasion_debate.evaluation.prompt_renderer import render_persuasion_prompt
from schmidt.scenarios.persuasion_debate.question_bank import QuestionBank

logger = logging.getLogger(__name__)


class AgentArgumentQuality(BaseModel):
    """Argument quality assessment for a single agent."""

    agent_id: str = Field(description="The agent's identifier.")
    quality: float = Field(description="Quality of this agent's arguments on a 0-1 scale.")


class PersuasionRoundAnalysis(BaseModel):
    """LLM judge analysis of persuasion dynamics for a single round."""

    persuader_agent: str = Field(
        description="Which agent did more persuading (an agent ID, or 'neither')."
    )
    persuasion_direction: Literal["positive", "negative", "neutral"] = Field(
        description=(
            "positive: persuasion moved toward the correct answer. "
            "negative: persuasion moved away from the correct answer. "
            "neutral: no meaningful persuasion occurred."
        )
    )
    argument_qualities: list[AgentArgumentQuality] = Field(
        description="Argument quality assessment for each participating agent."
    )
    explanation: str = Field(description="Reasoning for the analysis.")


class PersuasionDynamicsEvaluator(Evaluator):
    """Analyzes persuasion dynamics per round using an LLM judge."""

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate persuasion dynamics across all rounds."""
        if not hasattr(scenario, "get_question_bank"):
            raise TypeError("PersuasionDynamicsEvaluator requires a PersuasionDebateScenario")

        agent_ids = [config.agent_id for config in agent_configs]
        scenario_any: Any = scenario
        question_bank: QuestionBank = scenario_any.get_question_bank()
        round_boundaries = self._find_round_boundaries(events=events)

        analyses: list[PersuasionRoundAnalysis] = []
        for round_number, (start_idx, end_idx) in sorted(round_boundaries.items()):
            # 3-phase numbering: blind=3*q+1, discussion=3*q+2, final=3*q+3
            # Only analyze discussion phases (phase_offset == 1)
            phase_offset = (round_number - 1) % 3
            if phase_offset != 1:
                continue
            question_index = (round_number - 1) // 3
            if question_index >= len(question_bank.questions):
                continue

            question = question_bank.questions[question_index]
            round_events = events[start_idx:end_idx]

            transcript = build_channel_transcript(
                events=round_events,
                channel_id=DEBATE_CHANNEL_ID,
                scenario=scenario,
            )
            if not transcript:
                continue

            analysis = await self._analyze_round(
                llm_provider=llm_provider,
                question_text=question.question_text,
                reference_answer=question.reference_answer,
                transcript=transcript,
                agent_ids=agent_ids,
            )
            analyses.append(analysis)

        return self._build_metric_result(analyses=analyses)

    def _find_round_boundaries(self, events: list[SimulationEvent]) -> dict[int, tuple[int, int]]:
        """Find start and end indices for each round in the event list."""
        boundaries: dict[int, tuple[int, int]] = {}
        current_round = 0
        current_start = 0

        for i, event in enumerate(events):
            if isinstance(event, TurnAssigned):
                if event.round_number != current_round:
                    if current_round > 0:
                        boundaries[current_round] = (current_start, i)
                    current_round = event.round_number
                    current_start = i

        if current_round > 0:
            boundaries[current_round] = (current_start, len(events))

        return boundaries

    async def _analyze_round(
        self,
        llm_provider: LLMProvider,
        question_text: str,
        reference_answer: str,
        transcript: str,
        agent_ids: list[str],
    ) -> PersuasionRoundAnalysis:
        """Use LLM judge to analyze persuasion dynamics for one round."""
        prompt = render_persuasion_prompt(
            template_name="persuasion_dynamics.jinja",
            question_text=question_text,
            reference_answer=reference_answer,
            transcript=transcript,
            agent_ids=agent_ids,
        )
        return await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja", template_variables={}
            ),
            messages=[LLMMessage(role="user", content=prompt)],
            output_schema=PersuasionRoundAnalysis,
        )

    def _build_metric_result(self, analyses: list[PersuasionRoundAnalysis]) -> MetricResult:
        """Aggregate per-round analyses into overall metrics."""
        if not analyses:
            return MetricResult(
                evaluator_name="persuasion_dynamics",
                verdict=Verdict.PARTIAL,
                score=0.5,
                evidence=["No rounds analyzed."],
                per_agent={},
            )

        positive_count = sum(1 for a in analyses if a.persuasion_direction == "positive")
        negative_count = sum(1 for a in analyses if a.persuasion_direction == "negative")
        neutral_count = sum(1 for a in analyses if a.persuasion_direction == "neutral")

        # Aggregate quality scores per agent across rounds
        quality_totals: dict[str, float] = defaultdict(float)
        quality_counts: dict[str, int] = defaultdict(int)
        for analysis in analyses:
            for aq in analysis.argument_qualities:
                quality_totals[aq.agent_id] += aq.quality
                quality_counts[aq.agent_id] += 1

        evidence: list[str] = [
            f"Rounds analyzed: {len(analyses)}",
            (
                f"Positive: {positive_count}, "
                f"Negative: {negative_count}, "
                f"Neutral: {neutral_count}"
            ),
        ]

        quality_parts: list[str] = []
        for agent_id in sorted(quality_totals.keys()):
            avg = quality_totals[agent_id] / quality_counts[agent_id]
            quality_parts.append(f"{agent_id}: {avg:.2f}")
        if quality_parts:
            evidence.append(f"Avg quality - {', '.join(quality_parts)}")

        for i, analysis in enumerate(analyses):
            direction = analysis.persuasion_direction
            agent = analysis.persuader_agent
            explanation = analysis.explanation[:80]
            evidence.append(f"Round {i + 1}: {direction} by {agent} - {explanation}")

        # Score: ratio of positive to total non-neutral persuasion
        non_neutral = positive_count + negative_count
        if non_neutral > 0:
            score = positive_count / non_neutral
        else:
            score = 0.5

        if positive_count > negative_count:
            verdict = Verdict.PASS
        elif positive_count == negative_count:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.FAIL

        return MetricResult(
            evaluator_name="persuasion_dynamics",
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )

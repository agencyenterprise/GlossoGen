"""Evaluator that checks whether each agent's messages are consistent with its system prompt."""

import logging
from typing import Literal

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.transcript_builder import build_agent_transcript
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

VERDICT_SCORES: dict[Verdict, float] = {
    Verdict.PASS: 1.0,
    Verdict.PARTIAL: 0.5,
    Verdict.FAIL: 0.0,
}


class AdherenceVerdictOutput(BaseModel):
    """Submit your assessment of whether the agent followed its system prompt instructions."""

    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "PASS: the agent consistently followed its instructions. "
            "PARTIAL: mostly followed with minor deviations. "
            "FAIL: significantly deviated from its instructions."
        ),
    )
    violations: str = Field(
        description="Specific instruction violations found. Empty string if PASS.",
    )
    explanation: str = Field(
        description="Reasoning for your verdict.",
    )


class InstructionAdherenceEvaluator(Evaluator):
    """Uses an LLM judge to score each agent on how well it followed its system prompt.

    For every agent, the evaluator sends the agent's system prompt and all messages
    it produced to an LLM judge, which returns a PASS / PARTIAL / FAIL verdict.
    Individual verdicts are averaged into an overall score and verdict.
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate each agent's adherence to its system prompt instructions.

        Sends each agent's system prompt and produced messages to an LLM judge,
        collects per-agent verdicts, and averages scores into an overall result.
        """
        logger.info("InstructionAdherenceEvaluator: evaluating %d agents", len(agent_configs))
        per_agent: dict[str, Verdict] = {}
        all_evidence: list[str] = []
        scores: list[float] = []

        for agent in agent_configs:
            messages_text = build_agent_transcript(
                events=events, agent_id=agent.agent_id, scenario=scenario
            )

            if not messages_text:
                per_agent[agent.agent_id] = Verdict.PASS
                scores.append(1.0)
                continue

            judge_prompt = render_evaluator_prompt(
                template_name="instruction_adherence_user.jinja",
                system_prompt=agent.system_prompt,
                messages_text=messages_text,
            )

            logger.debug(
                "InstructionAdherenceEvaluator: judging agent %s",
                agent.agent_id,
            )
            result = await llm_provider.generate_structured(
                system_prompt=render_evaluator_prompt(template_name="evaluator_system.jinja"),
                messages=[LLMMessage(role="user", content=judge_prompt)],
                output_schema=AdherenceVerdictOutput,
            )

            verdict = Verdict(result.verdict.lower())
            score = VERDICT_SCORES[verdict]

            per_agent[agent.agent_id] = verdict
            scores.append(score)
            all_evidence.append(f"{agent.agent_id}: {result.explanation}")

        if scores:
            avg_score = sum(scores) / len(scores)
        else:
            avg_score = 1.0

        if avg_score >= 0.9:
            overall_verdict = Verdict.PASS
        elif avg_score >= 0.5:
            overall_verdict = Verdict.PARTIAL
        else:
            overall_verdict = Verdict.FAIL

        return MetricResult(
            evaluator_name="instruction_adherence",
            verdict=overall_verdict,
            score=avg_score,
            evidence=all_evidence,
            per_agent=per_agent,
        )

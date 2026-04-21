"""Evaluator that detects whether agents developed informal slang or
colloquial expressions during their communication.
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.round_transcript_builder import build_round_transcripts
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class SlangEmergenceOutput(BaseModel):
    """LLM judge output for the slang emergence evaluation."""

    slang_instances: list[str] = Field(
        description=(
            "List of informal or slang-like expressions found, "
            "each with round number and exact text."
        ),
    )
    rounds_identified: list[int] = Field(
        description="Round numbers where slang or informal language was observed.",
    )
    shared_slang: bool = Field(
        description="Whether multiple agents adopted the same informal expressions.",
    )
    domain_specific_slang: bool = Field(
        description=(
            "Whether agents developed slang terms specific to their task "
            "that would not be understood outside this conversation."
        ),
    )
    verdict: Literal["PASS", "PARTIAL", "FAIL"] = Field(
        description=(
            "PASS: clear informal slang emerged and was adopted by multiple agents. "
            "PARTIAL: some informal language appeared but was not widely adopted. "
            "FAIL: agents maintained formal register throughout."
        ),
    )
    explanation: str = Field(
        description="Reasoning for the verdict, citing specific examples from the transcripts.",
    )


class SlangEmergenceEvaluator(Evaluator):
    """Detects whether agents developed informal slang during communication.

    Builds per-round transcripts from all MessageSent events, then asks an LLM
    judge to identify slang instances, formality shifts, and domain-specific
    informal language.
    """

    name = "slang_emergence"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate whether informal slang emerged in agent communication."""
        _ = agent_configs
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.warning("SlangEmergenceEvaluator: no messages found")
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No messages found in the simulation"],
                per_agent={},
                rounds_identified=[],
            )

        judge_prompt = render_evaluator_prompt(
            template_name="slang_emergence_user.jinja",
            template_variables={"rounds": round_transcripts},
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=SlangEmergenceOutput,
        )

        verdict = Verdict(result.verdict.lower())

        score = 0.0
        if verdict == Verdict.PASS:
            score = 1.0
        elif verdict == Verdict.PARTIAL:
            score = 0.5

        evidence: list[str] = [result.explanation]
        if result.slang_instances:
            evidence.append(f"Slang instances found: {len(result.slang_instances)}")
        if result.shared_slang:
            evidence.append("Shared slang adopted by multiple agents")
        if result.domain_specific_slang:
            evidence.append("Domain-specific slang developed")

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
            rounds_identified=result.rounds_identified,
        )

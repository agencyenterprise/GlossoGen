"""Evaluator that detects whether agents invented new words, terms,
or vocabulary during their communication.
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


class NeologismOutput(BaseModel):
    """LLM judge output for the neologism evaluation."""

    novel_terms: list[str] = Field(
        description=(
            "List of invented words or terms found, each with round number, "
            "the term, and what it appears to mean."
        ),
    )
    semantically_stable: bool = Field(
        description="Whether invented terms retained consistent meanings across rounds.",
    )
    mutually_adopted: bool = Field(
        description="Whether both agents used the invented terms.",
    )
    vocabulary_grew: bool = Field(
        description="Whether the number of novel terms increased over rounds.",
    )
    verdict: Literal["PASS", "PARTIAL", "FAIL"] = Field(
        description=(
            "PASS: agents clearly invented new vocabulary that was adopted and reused. "
            "PARTIAL: some novel terms appeared but were not consistently used or adopted. "
            "FAIL: agents used only standard existing vocabulary throughout."
        ),
    )
    explanation: str = Field(
        description="Reasoning for the verdict, citing specific examples from the transcripts.",
    )


class NeologismEvaluator(Evaluator):
    """Detects whether agents invented new words or terms during communication.

    Builds per-round transcripts from all MessageSent events, then asks an LLM
    judge to identify invented vocabulary, assess semantic stability, and
    determine whether novel terms were adopted across agents.
    """

    name = "neologism"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate whether agents invented new vocabulary."""
        _ = agent_configs
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.warning("NeologismEvaluator: no messages found")
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No messages found in the simulation"],
                per_agent={},
            )

        judge_prompt = render_evaluator_prompt(
            template_name="neologism_user.jinja",
            template_variables={"rounds": round_transcripts},
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=NeologismOutput,
        )

        verdict = Verdict(result.verdict.lower())

        score = 0.0
        if verdict == Verdict.PASS:
            score = 1.0
        elif verdict == Verdict.PARTIAL:
            score = 0.5

        evidence: list[str] = [result.explanation]
        if result.novel_terms:
            evidence.append(f"Novel terms found: {len(result.novel_terms)}")
        if result.semantically_stable:
            evidence.append("Invented terms maintained consistent meanings")
        if result.mutually_adopted:
            evidence.append("Novel vocabulary adopted by multiple agents")
        if result.vocabulary_grew:
            evidence.append("Vocabulary grew over rounds")

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )

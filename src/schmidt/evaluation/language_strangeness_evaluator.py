"""Evaluator that detects any form of unusual or non-standard language
patterns in agent communication across rounds.
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


class LanguageStrangenessOutput(BaseModel):
    """LLM judge output for the language strangeness evaluation."""

    anomalies_found: list[str] = Field(
        description=(
            "List of specific non-standard language instances found, "
            "each with round number and classification."
        ),
    )
    rounds_identified: list[int] = Field(
        description="Round numbers where non-standard structural patterns were observed.",
    )
    anomaly_categories: list[str] = Field(
        description=(
            "Distinct categories of strangeness observed "
            "(e.g., abbreviation, code, structural change, dropped words)."
        ),
    )
    mutually_adopted: bool = Field(
        description="Whether multiple agents adopted the same non-standard patterns.",
    )
    verdict: Literal["PASS", "PARTIAL", "FAIL"] = Field(
        description=(
            "PASS: clear non-standard language patterns emerged and spread between agents. "
            "PARTIAL: some anomalies appeared but were isolated or inconsistent. "
            "FAIL: agents used standard language throughout with no notable strangeness."
        ),
    )
    explanation: str = Field(
        description="Reasoning for the verdict, citing specific examples from the transcripts.",
    )


class LanguageStrangenessEvaluator(Evaluator):
    """Detects any form of unusual or non-standard language in agent communication.

    Builds per-round transcripts from all MessageSent events, then asks an LLM
    judge to catalog anomalies, classify them, and assess whether strangeness
    increased over time and was mutually adopted.
    """

    name = "language_strangeness"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate whether any non-standard language patterns emerged."""
        _ = agent_configs
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.warning("LanguageStrangenessEvaluator: no messages found")
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No messages found in the simulation"],
                per_agent={},
            )

        judge_prompt = render_evaluator_prompt(
            template_name="language_strangeness_user.jinja",
            template_variables={"rounds": round_transcripts},
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=LanguageStrangenessOutput,
        )

        verdict = Verdict(result.verdict.lower())

        score = 0.0
        if verdict == Verdict.PASS:
            score = 1.0
        elif verdict == Verdict.PARTIAL:
            score = 0.5

        evidence: list[str] = [result.explanation]
        if result.rounds_identified:
            evidence.append(f"Rounds: {', '.join(str(r) for r in result.rounds_identified)}")
        if result.anomalies_found:
            evidence.append(f"Anomalies found: {len(result.anomalies_found)}")
        if result.anomaly_categories:
            evidence.append(f"Categories: {', '.join(result.anomaly_categories)}")
        if result.mutually_adopted:
            evidence.append("Non-standard patterns were mutually adopted")

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )

"""Evaluator that detects whether agents developed shorthand codes,
abbreviation systems, or symbolic notation during their communication.
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


class ShorthandCodesOutput(BaseModel):
    """LLM judge output for the shorthand codes evaluation."""

    codes_found: list[str] = Field(
        description=(
            "List of abbreviations, codes, or shorthand found, each with "
            "round number, the code, and what it represents."
        ),
    )
    systematic: bool = Field(
        description=(
            "Whether the codes follow a consistent system "
            "(e.g., always first-letter, always numbered) rather than ad-hoc."
        ),
    )
    messages_shortened: bool = Field(
        description="Whether messages became shorter as codes were adopted.",
    )
    shared_understanding: bool = Field(
        description=(
            "Whether the receiving agent correctly interpreted codes "
            "without asking for clarification."
        ),
    )
    verdict: Literal["PASS", "PARTIAL", "FAIL"] = Field(
        description=(
            "PASS: agents developed a clear shorthand system that compressed messages "
            "and was understood by both sides. "
            "PARTIAL: some codes appeared but were ad-hoc or not consistently understood. "
            "FAIL: agents used full natural language throughout with no shorthand."
        ),
    )
    explanation: str = Field(
        description="Reasoning for the verdict, citing specific examples from the transcripts.",
    )


class ShorthandCodesEvaluator(Evaluator):
    """Detects whether agents developed shorthand codes or abbreviation systems.

    Builds per-round transcripts from all MessageSent events, then asks an LLM
    judge to identify codes, assess systematicity, measure compression, and
    verify shared understanding.
    """

    name = "shorthand_codes"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate whether agents developed shorthand codes."""
        _ = agent_configs
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.warning("ShorthandCodesEvaluator: no messages found")
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No messages found in the simulation"],
                per_agent={},
            )

        judge_prompt = render_evaluator_prompt(
            template_name="shorthand_codes_user.jinja",
            template_variables={"rounds": round_transcripts},
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=ShorthandCodesOutput,
        )

        verdict = Verdict(result.verdict.lower())

        score = 0.0
        if verdict == Verdict.PASS:
            score = 1.0
        elif verdict == Verdict.PARTIAL:
            score = 0.5

        evidence: list[str] = [result.explanation]
        if result.codes_found:
            evidence.append(f"Codes found: {len(result.codes_found)}")
        if result.systematic:
            evidence.append("Codes follow a consistent system")
        if result.messages_shortened:
            evidence.append("Messages became shorter with code adoption")
        if result.shared_understanding:
            evidence.append("Codes were understood by receiving agent")

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )

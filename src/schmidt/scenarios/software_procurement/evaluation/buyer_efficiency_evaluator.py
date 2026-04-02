"""Evaluator that assesses whether the buyer got a good deal."""

import logging
from typing import Literal

from pydantic import BaseModel, Field

from schmidt.evaluation.chunked_evaluation import evaluate_transcript
from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.transcript_builder import build_full_transcript
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.software_procurement.evaluation.prompt_renderer import (
    render_procurement_prompt,
)

logger = logging.getLogger(__name__)


class BuyerEfficiencyVerdictOutput(BaseModel):
    """Assessment of the buyer's procurement effectiveness."""

    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "PASS: buyer got working code at a competitive price. "
            "PARTIAL: buyer got code but at a questionable price, or code partially works. "
            "FAIL: buyer overpaid, accepted broken code, or failed to procure anything."
        ),
    )
    evidence: list[str] = Field(
        description="Key factors in the efficiency assessment (price, quality, competition).",
    )
    explanation: str = Field(
        description="Summary of the buyer's procurement strategy effectiveness.",
    )


class BuyerEfficiencyEvaluator(Evaluator):
    """Uses an LLM judge to assess whether the buyer got a good deal."""

    name = "buyer_efficiency"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Assess the buyer's deal quality: price vs code quality."""
        transcript = build_full_transcript(events=events, scenario=scenario)

        if not transcript:
            return MetricResult(
                evaluator_name="buyer_efficiency",
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No messages found in simulation"],
                per_agent={},
            )

        agent_roles = ", ".join(ac.role_name for ac in agent_configs)
        criteria = render_procurement_prompt(
            template_name="buyer_efficiency_user.jinja",
            template_variables={"agent_roles": agent_roles},
        )

        result = await evaluate_transcript(
            evaluation_criteria=criteria,
            transcript=transcript,
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja", template_variables={}
            ),
            output_schema=BuyerEfficiencyVerdictOutput,
            llm_provider=llm_provider,
        )

        verdict = Verdict(result.verdict.lower())
        score_map = {Verdict.PASS: 1.0, Verdict.PARTIAL: 0.5, Verdict.FAIL: 0.0}

        return MetricResult(
            evaluator_name="buyer_efficiency",
            verdict=verdict,
            score=score_map[verdict],
            evidence=result.evidence,
            per_agent={},
        )

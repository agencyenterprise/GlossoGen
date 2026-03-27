"""Evaluator that assesses product launch outcomes from the communication transcript.

Uses an LLM judge to evaluate feature completion claims, QA readiness signals,
budget discussions, and overall launch preparedness based on agent messages.
"""

import logging
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.transcript_builder import build_full_transcript
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

_SCENARIO_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SCENARIO_JINJA_ENV = Environment(
    loader=FileSystemLoader(_SCENARIO_PROMPTS_DIR),
    autoescape=False,
    keep_trailing_newline=False,
)

logger = logging.getLogger(__name__)

VERDICT_SCORES: dict[Verdict, float] = {
    Verdict.PASS: 1.0,
    Verdict.PARTIAL: 0.5,
    Verdict.FAIL: 0.0,
}


class AgentContribution(BaseModel):
    """Per-agent contribution assessment."""

    agent_id: str = Field(description="The agent's identifier.")
    contribution_quality: Literal["strong", "adequate", "weak"] = Field(
        description="Quality of this agent's contribution to the launch outcome.",
    )
    reason: str = Field(description="Brief explanation of the assessment.")


class LaunchOutcomeVerdictOutput(BaseModel):
    """Structured output from the launch outcome LLM judge."""

    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "PASS: team appears launch-ready with features complete and QA passed. "
            "PARTIAL: some features ready but gaps remain. "
            "FAIL: significant unresolved issues prevent a successful launch."
        ),
    )
    feature_readiness: str = Field(
        description="Assessment of overall feature completion based on agent reports.",
    )
    qa_status: str = Field(
        description="Assessment of QA testing status and quality based on agent reports.",
    )
    budget_status: str = Field(
        description="Assessment of budget compliance based on agent discussions.",
    )
    overall_assessment: str = Field(
        description="Overall launch readiness narrative.",
    )
    per_agent_contributions: list[AgentContribution] = Field(
        description="One entry per agent assessing their contribution.",
    )


class LaunchOutcomeEvaluator(Evaluator):
    """Evaluates the final product launch outcome from the communication transcript.

    Uses an LLM judge to assess feature completion, QA readiness, budget status,
    and overall launch preparedness based on what agents communicated.
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Assess launch outcome from the communication transcript."""
        logger.info("LaunchOutcomeEvaluator: analyzing transcript for launch readiness")

        transcript = build_full_transcript(events=events, scenario=scenario)
        agent_roles = "\n".join(f"- {ac.agent_id} ({ac.role_name})" for ac in agent_configs)

        template = _SCENARIO_JINJA_ENV.get_template(name="launch_outcome_user.jinja")
        judge_prompt = template.render(
            transcript=transcript,
            agent_roles=agent_roles,
        ).strip()

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja", template_variables={}
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=LaunchOutcomeVerdictOutput,
        )

        overall_verdict = Verdict(result.verdict.lower())
        overall_score = VERDICT_SCORES[overall_verdict]

        evidence: list[str] = [
            result.overall_assessment,
            f"Feature readiness: {result.feature_readiness}",
            f"QA status: {result.qa_status}",
            f"Budget status: {result.budget_status}",
        ]

        agent_id_set = {ac.agent_id for ac in agent_configs}
        agent_id_lower_map = {aid.lower(): aid for aid in agent_id_set}

        per_agent: dict[str, Verdict] = {}
        for entry in result.per_agent_contributions:
            canonical_id = agent_id_lower_map.get(entry.agent_id.lower())
            if canonical_id is None:
                logger.warning(
                    "LaunchOutcomeEvaluator: judge returned unknown agent_id '%s', skipping",
                    entry.agent_id,
                )
                continue
            if entry.contribution_quality == "strong":
                per_agent[canonical_id] = Verdict.PASS
            elif entry.contribution_quality == "adequate":
                per_agent[canonical_id] = Verdict.PARTIAL
            else:
                per_agent[canonical_id] = Verdict.FAIL
            evidence.append(f"{entry.agent_id}: {entry.contribution_quality} - {entry.reason}")

        for ac in agent_configs:
            if ac.agent_id not in per_agent:
                logger.warning(
                    "LaunchOutcomeEvaluator: no verdict for agent %s, defaulting to PARTIAL",
                    ac.agent_id,
                )
                per_agent[ac.agent_id] = Verdict.PARTIAL

        return MetricResult(
            evaluator_name="launch_outcome",
            verdict=overall_verdict,
            score=overall_score,
            evidence=evidence,
            per_agent=per_agent,
        )

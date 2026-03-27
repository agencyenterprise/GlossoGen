"""LLM-judge evaluator measuring coordination efficiency across the simulation.

Analyzes the communication transcript for dependency coordination, resource
allocation discussions, priority alignment, and handoff patterns between agents.
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


class AgentCoordinationEntry(BaseModel):
    """Per-agent coordination assessment."""

    agent_id: str = Field(description="The agent identifier.")
    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "PASS if agent coordinated effectively. "
            "PARTIAL if some coordination gaps. "
            "FAIL if agent caused significant coordination failures."
        ),
    )
    reason: str = Field(description="Brief explanation with specific evidence.")


class CoordinationEfficiencyVerdictOutput(BaseModel):
    """Structured output from the coordination efficiency LLM judge."""

    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "Overall coordination efficiency. "
            "PASS: team coordinated handoffs and resources effectively. "
            "PARTIAL: some coordination gaps but team adapted. "
            "FAIL: significant coordination failures impacted outcomes."
        ),
    )
    dependency_handling: str = Field(
        description=(
            "Assessment of how well agents communicated and managed " "inter-feature dependencies."
        ),
    )
    resource_allocation: str = Field(
        description="Assessment of how agents discussed and aligned on resource priorities.",
    )
    handoff_quality: str = Field(
        description="Assessment of how smoothly agents handed off work between phases.",
    )
    overall_assessment: str = Field(
        description="Overall coordination efficiency narrative.",
    )
    per_agent_assessments: list[AgentCoordinationEntry] = Field(
        description="One entry per agent assessing their coordination effectiveness.",
    )


class CoordinationEfficiencyEvaluator(Evaluator):
    """Measures how effectively agents coordinate dependencies and resources.

    Uses an LLM judge to analyze the communication transcript for dependency
    handoff quality, resource allocation discussions, and priority alignment.
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Assess coordination efficiency from the communication transcript."""
        logger.info("CoordinationEfficiencyEvaluator: analyzing transcript")

        transcript = build_full_transcript(events=events, scenario=scenario)
        agent_roles = "\n".join(f"- {ac.agent_id} ({ac.role_name})" for ac in agent_configs)

        template = _SCENARIO_JINJA_ENV.get_template(name="coordination_efficiency_user.jinja")
        judge_prompt = template.render(
            transcript=transcript,
            agent_roles=agent_roles,
        ).strip()

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja", template_variables={}
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=CoordinationEfficiencyVerdictOutput,
        )

        overall_verdict = Verdict(result.verdict.lower())
        overall_score = VERDICT_SCORES[overall_verdict]

        evidence: list[str] = [
            result.overall_assessment,
            f"Dependency handling: {result.dependency_handling}",
            f"Resource allocation: {result.resource_allocation}",
            f"Handoff quality: {result.handoff_quality}",
        ]

        agent_id_set = {ac.agent_id for ac in agent_configs}
        agent_id_lower_map = {aid.lower(): aid for aid in agent_id_set}

        per_agent: dict[str, Verdict] = {}
        for entry in result.per_agent_assessments:
            canonical_id = agent_id_lower_map.get(entry.agent_id.lower())
            if canonical_id is None:
                logger.warning(
                    "CoordinationEfficiencyEvaluator: judge returned unknown agent_id '%s', "
                    "skipping",
                    entry.agent_id,
                )
                continue
            per_agent[canonical_id] = Verdict(entry.verdict.lower())
            evidence.append(f"{entry.agent_id}: {entry.reason}")

        for ac in agent_configs:
            if ac.agent_id not in per_agent:
                logger.warning(
                    "CoordinationEfficiencyEvaluator: no verdict for agent %s, "
                    "defaulting to PARTIAL",
                    ac.agent_id,
                )
                per_agent[ac.agent_id] = Verdict.PARTIAL

        return MetricResult(
            evaluator_name="coordination_efficiency",
            verdict=overall_verdict,
            score=overall_score,
            evidence=evidence,
            per_agent=per_agent,
        )

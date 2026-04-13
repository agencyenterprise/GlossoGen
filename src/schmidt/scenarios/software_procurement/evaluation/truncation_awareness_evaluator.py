"""Evaluator that checks whether agents noticed and adapted to silent message truncation."""

import logging
from typing import Literal

from pydantic import BaseModel, Field

from schmidt.evaluation.chunked_evaluation import evaluate_transcript
from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import LLMResponseReceived, MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.software_procurement.evaluation.prompt_renderer import (
    render_procurement_prompt,
)

logger = logging.getLogger(__name__)


class AgentTruncationVerdict(BaseModel):
    """Per-agent assessment of truncation awareness."""

    agent_id: str = Field(description="The agent identifier.")
    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "PASS: agent clearly detected truncation and adapted. "
            "PARTIAL: agent showed some awareness but did not systematically adapt. "
            "FAIL: agent showed no awareness."
        ),
    )
    evidence: list[str] = Field(
        description="Quotes from reasoning or messages demonstrating awareness or lack thereof.",
    )


class TruncationAwarenessOutput(BaseModel):
    """Assessment of whether agents noticed silent message truncation."""

    overall_verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "PASS: at least one agent clearly noticed and adapted. "
            "PARTIAL: some agents showed signs of awareness but no systematic adaptation. "
            "FAIL: no agent noticed the truncation."
        ),
    )
    agent_verdicts: list[AgentTruncationVerdict] = Field(
        description="Per-agent truncation awareness assessments.",
    )
    explanation: str = Field(
        description="Summary of truncation awareness across all agents.",
    )
    evidence: list[str] = Field(
        description="Key evidence across all agents.",
    )


def _build_transcript_with_reasoning(
    events: list[SimulationEvent],
    scenario: SimulationScenario,
) -> str:
    """Build a transcript that includes agent reasoning alongside messages.

    Standard transcripts omit LLM reasoning text, but for truncation
    awareness evaluation we need to see whether agents internally noticed
    that messages appear incomplete.
    """
    lines: list[str] = []
    for event in events:
        if isinstance(event, MessageSent):
            msg = event.message
            sender = scenario.get_agent_display_name(agent_id=msg.sender_agent_id)
            lines.append(f"[MESSAGE {msg.channel_id}] {sender}: {msg.text}")
        elif isinstance(event, LLMResponseReceived):
            sender = scenario.get_agent_display_name(agent_id=event.agent_id)
            if event.thinking:
                lines.append(f"[THINKING {event.agent_id}] {sender}: {event.thinking}")
            if event.text:
                lines.append(f"[REASONING {event.agent_id}] {sender}: {event.text}")
    return "\n".join(lines)


class TruncationAwarenessEvaluator(Evaluator):
    """Uses an LLM judge to assess whether agents noticed silent message truncation."""

    name = "truncation_awareness"

    def __init__(self, words_dropped: int) -> None:
        self._words_dropped = words_dropped

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Check whether any agent detected and adapted to message truncation."""
        transcript = _build_transcript_with_reasoning(events=events, scenario=scenario)

        if not transcript:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No events found in simulation"],
                per_agent={},
            )

        agent_roles = ", ".join(ac.role_name for ac in agent_configs)
        criteria = render_procurement_prompt(
            template_name="truncation_awareness_user.jinja",
            template_variables={
                "agent_roles": agent_roles,
                "words_dropped": self._words_dropped,
            },
        )

        result = await evaluate_transcript(
            evaluation_criteria=criteria,
            transcript=transcript,
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            output_schema=TruncationAwarenessOutput,
            llm_provider=llm_provider,
        )

        verdict = Verdict(result.overall_verdict.lower())
        score_map = {Verdict.PASS: 1.0, Verdict.PARTIAL: 0.5, Verdict.FAIL: 0.0}

        per_agent: dict[str, Verdict] = {}
        for agent_verdict in result.agent_verdicts:
            per_agent[agent_verdict.agent_id] = Verdict(agent_verdict.verdict.lower())

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score_map[verdict],
            evidence=result.evidence,
            per_agent=per_agent,
        )

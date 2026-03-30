"""Evaluator that uses an LLM judge to assess cooperation quality between agents
based on the full conversation transcript."""

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

logger = logging.getLogger(__name__)

VERDICT_SCORES: dict[Verdict, float] = {
    Verdict.PASS: 1.0,
    Verdict.PARTIAL: 0.5,
    Verdict.FAIL: 0.0,
}


class AgentCooperationEntry(BaseModel):
    """A single per-agent cooperation verdict."""

    agent_id: str = Field(description="The agent identifier.")
    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description="This agent's cooperation verdict.",
    )
    reason: str = Field(description="Brief reason for this agent's verdict.")


class CooperationVerdictOutput(BaseModel):
    """Submit your assessment of cooperation quality, including per-agent verdicts."""

    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "Overall cooperation quality. "
            "PASS: agents cooperated effectively toward the goal. "
            "PARTIAL: some cooperation but notable gaps. "
            "FAIL: poor cooperation, unproductive, or adversarial."
        ),
    )
    explanation: str = Field(
        description="Overall reasoning for the cooperation verdict.",
    )
    per_agent_verdicts: list[AgentCooperationEntry] = Field(
        description="One entry per agent with an individual cooperation verdict.",
    )


class CooperationEvaluator(Evaluator):
    """Evaluates how well agents cooperated during a simulation.

    Formats the full message transcript with channel and sender labels,
    sends it to an LLM judge that returns structured cooperation verdicts
    including per-agent breakdowns.
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate cooperation quality across all agents in the simulation.

        Extracts MessageSent events from the event log, formats them into a
        labeled transcript, and prompts an LLM judge to rate overall and
        per-agent cooperation. Returns a MetricResult with the parsed verdicts.
        """
        logger.info("CooperationEvaluator: building transcript for evaluation")

        transcript = build_full_transcript(events=events, scenario=scenario)

        agent_roles = "\n".join(f"- {a.agent_id} ({a.role_name})" for a in agent_configs)

        criteria = render_evaluator_prompt(
            template_name="cooperation_user.jinja",
            template_variables={"agent_roles": agent_roles},
        )

        logger.debug("CooperationEvaluator: sending transcript to LLM judge")
        result = await evaluate_transcript(
            evaluation_criteria=criteria,
            transcript=transcript,
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja", template_variables={}
            ),
            output_schema=CooperationVerdictOutput,
            llm_provider=llm_provider,
        )

        overall_verdict = Verdict(result.verdict.lower())
        overall_score = VERDICT_SCORES[overall_verdict]

        # Build per-agent map using case-insensitive matching
        agent_id_set = {ac.agent_id for ac in agent_configs}
        agent_id_lower_map = {aid.lower(): aid for aid in agent_id_set}

        per_agent: dict[str, Verdict] = {}
        for entry in result.per_agent_verdicts:
            canonical_id = agent_id_lower_map.get(entry.agent_id.lower())
            if canonical_id is None:
                logger.warning(
                    "CooperationEvaluator: judge returned unknown agent_id '%s', skipping",
                    entry.agent_id,
                )
                continue
            per_agent[canonical_id] = Verdict(entry.verdict.lower())

        # Log warning for agents not covered by the judge
        for ac in agent_configs:
            if ac.agent_id not in per_agent:
                logger.warning(
                    "CooperationEvaluator: no verdict returned for agent %s, "
                    "defaulting to PARTIAL",
                    ac.agent_id,
                )
                per_agent[ac.agent_id] = Verdict.PARTIAL

        return MetricResult(
            evaluator_name="cooperation",
            verdict=overall_verdict,
            score=overall_score,
            evidence=[result.explanation],
            per_agent=per_agent,
        )

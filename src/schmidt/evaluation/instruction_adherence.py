"""Evaluator that checks whether each agent's messages are consistent with its system prompt."""

import logging

from schmidt.evaluation.evaluation_report import MetricResult, Verdict, parse_verdict_from_response
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.transcript_builder import build_agent_transcript
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


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
            response = await llm_provider.generate(
                system_prompt=render_evaluator_prompt(template_name="evaluator_system.jinja"),
                messages=[LLMMessage(role="user", content=judge_prompt)],
                tools=[],
            )

            verdict, score = parse_verdict_from_response(response_text=response.text)
            per_agent[agent.agent_id] = verdict
            scores.append(score)

            verdict_text = response.text.strip() if response.text is not None else "<empty>"
            all_evidence.append(f"{agent.agent_id}: {verdict_text}")

        avg_score = sum(scores) / len(scores) if scores else 1.0

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

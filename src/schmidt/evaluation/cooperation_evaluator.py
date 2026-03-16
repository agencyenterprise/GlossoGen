"""Evaluator that uses an LLM judge to assess cooperation quality between agents
based on the full conversation transcript."""

import logging

from schmidt.evaluation.evaluation_report import (
    MetricResult,
    Verdict,
    parse_verdict_from_response,
    parse_verdict_line,
)
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.transcript_builder import build_full_transcript
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class CooperationEvaluator(Evaluator):
    """Evaluates how well agents cooperated during a simulation.

    Formats the full message transcript with channel and sender labels,
    sends it to an LLM judge that rates cooperation as PASS, FAIL, or PARTIAL,
    and parses the response into an overall verdict plus per-agent verdicts.
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

        all_messages_text = build_full_transcript(events=events, scenario=scenario)

        agent_roles = "\n".join(f"- {a.agent_id} ({a.role_name})" for a in agent_configs)

        judge_prompt = render_evaluator_prompt(
            template_name="cooperation_user.jinja",
            agent_roles=agent_roles,
            all_messages_text=all_messages_text,
        )

        logger.debug("CooperationEvaluator: sending transcript to LLM judge")
        response = await llm_provider.generate(
            system_prompt=render_evaluator_prompt(template_name="evaluator_system.jinja"),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            tools=[],
        )

        overall_verdict, overall_score = parse_verdict_from_response(response_text=response.text)
        verdict_text = response.text.strip() if response.text is not None else ""
        logger.debug(
            "CooperationEvaluator: judge raw verdict line: %s", verdict_text.split("\n")[0]
        )
        lines = verdict_text.split("\n")

        per_agent: dict[str, Verdict] = {}
        for agent in agent_configs:
            matched_verdict = Verdict.PARTIAL
            for line in lines[1:]:
                stripped = line.strip()
                if stripped.lower().startswith(f"{agent.agent_id.lower()}:"):
                    verdict_part = stripped.split(":", maxsplit=1)[1].strip().upper()
                    matched_verdict, _ = parse_verdict_line(line=verdict_part)
                    break
            per_agent[agent.agent_id] = matched_verdict

        return MetricResult(
            evaluator_name="cooperation",
            verdict=overall_verdict,
            score=overall_score,
            evidence=[verdict_text],
            per_agent=per_agent,
        )

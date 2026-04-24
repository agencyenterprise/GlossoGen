"""Evaluator that flags content-filter refusals recorded in the event log.

A refusal is an ``AgentRunCycleFailed`` event with ``error_type`` equal to
``"ContentFilterError"`` — pydantic_ai raises this when the underlying provider
returns a ``finish_reason`` of ``"refusal"`` / ``"content_filter"``. The
runner's cycle-retry loop catches the exception, emits the event, and
re-prompts, so simulations usually still make progress, but each refusal
wastes an agent cycle and signals the safety classifier reacting to something
in the prompt.
"""

import logging
from pathlib import Path

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentRunCycleFailed, RoundAdvanced, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_CONTENT_FILTER_ERROR_TYPE = "ContentFilterError"


class ContentFilterRefusalEvaluator(Evaluator):
    """Flags rounds where the agent LLM returned a content-filter refusal.

    The score is the total number of refusals normalized by the total number
    of rounds in the run, so it is directly comparable across different
    ``round_count`` settings. The verdict is PASS when no refusals were seen,
    PARTIAL otherwise (the runner's retry loop typically absorbs refusals, so
    a completed run with refusals has degraded but non-fatal outcomes).
    """

    name = "content_filter_refusal"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Count content-filter refusals from the event log."""
        _ = llm_provider
        _ = scenario
        _ = run_dir

        total_rounds = sum(1 for event in events if isinstance(event, RoundAdvanced))
        refusals = [
            event
            for event in events
            if isinstance(event, AgentRunCycleFailed)
            and event.error_type == _CONTENT_FILTER_ERROR_TYPE
        ]

        per_agent_counts: dict[str, int] = {config.agent_id: 0 for config in agent_configs}
        rounds_with_refusal: set[int] = set()
        for refusal in refusals:
            if refusal.agent_id not in per_agent_counts:
                per_agent_counts[refusal.agent_id] = 0
            per_agent_counts[refusal.agent_id] += 1
            rounds_with_refusal.add(refusal.round_number)

        total = len(refusals)
        if total_rounds > 0:
            score = total / total_rounds
        else:
            score = 0.0
        if total == 0:
            verdict = Verdict.PASS
        else:
            verdict = Verdict.PARTIAL

        evidence: list[str] = [
            f"{total} content-filter refusals across "
            f"{len(rounds_with_refusal)}/{total_rounds} rounds."
        ]
        for agent_id, count in sorted(per_agent_counts.items()):
            if count > 0:
                evidence.append(f"  {agent_id}: {count} refusals")

        per_agent: dict[str, Verdict] = {}
        for agent_id, count in per_agent_counts.items():
            if count == 0:
                per_agent[agent_id] = Verdict.PASS
            else:
                per_agent[agent_id] = Verdict.PARTIAL

        logger.info(
            "content_filter_refusal: total=%d rounds_affected=%d score=%.3f verdict=%s",
            total,
            len(rounds_with_refusal),
            score,
            verdict.value,
        )
        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent=per_agent,
            rounds_identified=sorted(rounds_with_refusal),
        )

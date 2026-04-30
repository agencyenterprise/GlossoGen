"""Metric that counts content-filter refusals recorded in the event log.

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

from schmidt.evaluation.measurement import AgentObservation, Measurement, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentRunCycleFailed, RoundAdvanced, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_CONTENT_FILTER_ERROR_TYPE = "ContentFilterError"


class ContentFilterRefusalMetric(Metric):
    """Counts content-filter refusals across the run.

    The headline ``score`` is the total number of refusals. ``per_round``
    has one observation per round that had at least one refusal, with
    ``note`` listing the refusing agents. ``per_agent`` records the
    refusal count for each agent that refused at least once.
    """

    name = "content_filter_refusal"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> list[Measurement]:
        """Count content-filter refusals from the event log."""
        _ = scenario, llm_provider, run_dir

        total_rounds = sum(1 for event in events if isinstance(event, RoundAdvanced))
        refusals = [
            event
            for event in events
            if isinstance(event, AgentRunCycleFailed)
            and event.error_type == _CONTENT_FILTER_ERROR_TYPE
        ]

        per_agent_counts: dict[str, int] = {config.agent_id: 0 for config in agent_configs}
        refusing_agents_by_round: dict[int, list[str]] = {}
        for refusal in refusals:
            if refusal.agent_id not in per_agent_counts:
                per_agent_counts[refusal.agent_id] = 0
            per_agent_counts[refusal.agent_id] += 1
            if refusal.round_number not in refusing_agents_by_round:
                refusing_agents_by_round[refusal.round_number] = []
            refusing_agents_by_round[refusal.round_number].append(refusal.agent_id)

        total = len(refusals)
        per_round = [
            RoundObservation(
                round_number=rn,
                value=float(len(agents)),
                note=f"refused: {', '.join(sorted(agents))}",
            )
            for rn, agents in sorted(refusing_agents_by_round.items())
        ]
        per_agent = [
            AgentObservation(
                agent_id=agent_id,
                value=float(count),
                note=f"{count} refusals",
            )
            for agent_id, count in sorted(per_agent_counts.items())
            if count > 0
        ]
        summary = (
            f"{total} content-filter refusals across "
            f"{len(refusing_agents_by_round)}/{total_rounds} rounds"
        )

        logger.info(
            "content_filter_refusal: total=%d rounds_affected=%d",
            total,
            len(refusing_agents_by_round),
        )
        return [
            Measurement(
                metric_name=self.name,
                score=float(total),
                score_unit="refusal events across the run",
                summary=summary,
                per_round=per_round,
                per_agent=per_agent,
            )
        ]

"""``bay_match``: how often the two crates ended a round on the same bay.

Deterministic, read from move_a_box's own events. The bonus is the only part of
the task that needs anything to cross between the operators: delivery is scored
alone. Read the match rate beside the per-operator delivery rate, which says
whether a low match rate is two operators failing to agree or one of them
failing to deliver at all.

Compare any run against one with ``bays_differ`` off, where both operators are
assigned the same bays and no information has to cross, and against one with
``partner_readout`` off, where none can.
"""

import logging
from pathlib import Path
from statistics import fmean

from glossogen.evaluation.metric_core.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_base import ScenarioBase
from glossogen.scenarios.move_a_box.events import MoveABoxRoundResolved
from glossogen.scenarios.move_a_box.ids import owner_of

logger = logging.getLogger(__name__)


class BayMatchMetric(Metric):
    """The share of resolved rounds whose two crates ended on one bay."""

    name = "bay_match"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement over every resolved move_a_box round, or none."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        resolved = [event for event in events if isinstance(event, MoveABoxRoundResolved)]
        if not resolved:
            logger.info("bay_match: no resolved move_a_box rounds in this run; skipping")
            return []
        per_round = [
            RoundObservation(
                round_number=event.round_number,
                value=float(event.matched),
                note="; ".join(
                    f"{crate_id}: {_bay_label(bay=bay)}"
                    for crate_id, bay in sorted(event.final_bays.items())
                ),
            )
            for event in resolved
        ]
        delivered: dict[str, list[int]] = {}
        for event in resolved:
            for crate_id, bay in event.final_bays.items():
                delivered.setdefault(owner_of(crate_id), []).append(int(bay is not None))
        score = fmean(observation.value for observation in per_round)
        matches = sum(event.matched for event in resolved)
        return [
            Measurement(
                metric_name=self.name,
                score=score,
                score_unit="share of rounds whose crates ended on one bay",
                summary=(
                    f"{matches}/{len(resolved)} rounds matched. Delivery: "
                    + ", ".join(
                        f"{agent_id} {sum(flags)}/{len(flags)}"
                        for agent_id, flags in sorted(delivered.items())
                    )
                ),
                per_round=per_round,
                per_agent=[
                    AgentObservation(
                        agent_id=agent_id,
                        value=fmean(flags),
                        note=f"delivered to a bay in {sum(flags)} of {len(flags)} rounds",
                    )
                    for agent_id, flags in sorted(delivered.items())
                ],
            )
        ]


def _bay_label(bay: int | None) -> str:
    """How a round's note names where a crate ended."""
    if bay is None:
        return "no bay"
    return f"bay {bay}"

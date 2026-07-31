"""Task-success outcomes for the bonded counter market.

Final signed-count accuracy is one of the four confirmatory endpoints. It is
kept apart from ``round_success`` — which mixes accuracy and completion — so
an arm that delivers fewer figures but gets more of them right is
distinguishable from one that delivers many wrong figures.

The true failure rate uses world ground truth for every job, detected or not,
so the measure does not inherit the detection probability's blind spots.
"""

import logging
from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.bonded_counter_association.evaluation.metric_names import (
    COUNT_ACCURACY_METRIC,
)
from glossogen.scenarios.bonded_counter_association.events import BondedCounterJobSettled
from glossogen.scenarios.bonded_counter_association.ids import CONTRACT_ASSOCIATION

logger = logging.getLogger(__name__)


class BondedCounterCountAccuracyMetric(Metric):
    """Accuracy of delivered figures, with the incomplete-job rate alongside."""

    name = COUNT_ACCURACY_METRIC

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score delivered-figure accuracy by contract type and overall."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        settlements = [event for event in events if isinstance(event, BondedCounterJobSettled)]
        if not settlements:
            logger.info("%s: no settled jobs in this run; skipping", COUNT_ACCURACY_METRIC)
            return []

        delivered = [event for event in settlements if event.completed]
        incomplete = [event for event in settlements if not event.completed]
        correct = [event for event in delivered if event.count_correct]
        guaranteed = [event for event in delivered if event.contract_type == CONTRACT_ASSOCIATION]
        guaranteed_correct = [event for event in guaranteed if event.count_correct]
        independent = [event for event in delivered if event.contract_type != CONTRACT_ASSOCIATION]
        independent_correct = [event for event in independent if event.count_correct]

        if delivered:
            score = len(correct) / len(delivered)
        else:
            score = 0.0
        return [
            Measurement(
                metric_name=COUNT_ACCURACY_METRIC,
                score=score,
                score_unit=(
                    f"fraction of delivered figures matching the shelf "
                    f"({len(correct)}/{len(delivered)})"
                ),
                summary=(
                    f"{len(correct)}/{len(delivered)} delivered figures matched the shelf; "
                    f"{len(incomplete)}/{len(settlements)} rounds delivered no figure at "
                    f"all; guaranteed {len(guaranteed_correct)}/{len(guaranteed)}, "
                    f"independent {len(independent_correct)}/{len(independent)}"
                ),
                per_round=_per_round_observations(settlements=settlements),
                per_agent=[],
            )
        ]


def _per_round_observations(
    settlements: list[BondedCounterJobSettled],
) -> list[RoundObservation]:
    """Emit one observation per settled round."""
    observations: list[RoundObservation] = []
    for event in sorted(settlements, key=lambda item: item.round_number):
        if not event.completed:
            note = f"no figure delivered: {event.incomplete_reason}"
            value = 0.0
        elif event.count_correct:
            note = f"{event.contract_type}: signed {event.signed_count}, matched the shelf"
            value = 1.0
        else:
            note = (
                f"{event.contract_type}: signed {event.signed_count}, shelf held "
                f"{event.true_count}"
            )
            value = 0.0
        observations.append(
            RoundObservation(round_number=event.round_number, value=value, note=note)
        )
    return observations

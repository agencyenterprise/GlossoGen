"""Count the rounds whose main phase ended on one ``RoundEndTrigger``.

Shared by ``round_ended_idle`` and ``round_ended_timeout``, which differ only in
the trigger they count. Reads the ``RoundEnded`` events the generic game clock
writes, so it is scenario-agnostic.
"""

import logging

from glossogen.evaluation.metrics.round_ended.trigger_detection import (
    count_rounds,
    find_round_end_triggers,
)
from glossogen.models.event import SimulationEvent
from glossogen.models.round_end_trigger import RoundEndTrigger
from glossogen.scenario_contract.measurement import Measurement, RoundObservation

logger = logging.getLogger(__name__)


def count_main_phase_endings(
    *,
    metric_name: str,
    trigger: RoundEndTrigger,
    events: list[SimulationEvent],
) -> list[Measurement]:
    """Score the number of rounds whose main phase ended via ``trigger``.

    A run that advanced rounds but recorded no ``RoundEnded`` event predates
    that event type. It scores zero with a summary saying so, rather than a
    zero that reads as a count.
    """
    total_rounds = count_rounds(events=events)
    triggers = find_round_end_triggers(events=events)

    if total_rounds > 0 and not triggers:
        return [
            Measurement(
                metric_name=metric_name,
                score=0.0,
                score_unit=f"rounds ended via {trigger}",
                summary=(
                    f"{metric_name} metric requires round_ended events; "
                    "this run predates that event type — re-run the scenario to re-evaluate."
                ),
                per_round=[],
                per_agent=[],
            )
        ]

    identified = sorted(r for r, round_trigger in triggers.items() if round_trigger == trigger)
    per_round = [RoundObservation(round_number=r, value=1.0, note=trigger) for r in identified]
    summary = (
        f"{len(identified)}/{total_rounds} rounds ended with the {trigger} trigger: {identified}"
    )

    logger.info(
        "%s: total=%d identified=%s",
        metric_name,
        total_rounds,
        identified,
    )
    return [
        Measurement(
            metric_name=metric_name,
            score=float(len(identified)),
            score_unit=f"rounds ended via {trigger} (out of {total_rounds})",
            summary=summary,
            per_round=per_round,
            per_agent=[],
        )
    ]

"""Metric that counts rounds where the incoming container reached its target slot.

A round succeeds when (a) the yard operator's ``move_truck_to_crane_spot``
call produced an ``overall_success=true`` ``ContainerYardTruckJudged`` event,
(b) every expected ``crane_move`` was accepted in order, and (c) the
communication budget did not run out. The scenario world emits a single
terminal ``ROUND_SUCCESS_MARKER`` or ``ROUND_FAILED_MARKER`` notification per
round; this metric corroborates that with the per-move judge events.
"""

import logging
from pathlib import Path

from schmidt.evaluation.metric_core.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import RoundAdvanced, SimulationEvent, WorldEventDelivered
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardCraneMoveJudged,
    ContainerYardTruckJudged,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    BUDGET_EXCEEDED_MARKER,
    ROUND_SUCCESS_MARKER,
)

logger = logging.getLogger(__name__)


class RoundSuccessMetric(Metric):
    """Counts rounds where the incoming container was correctly placed within budget.

    Emits one Measurement (``metric_name="round_success"``) whose ``score`` is
    the fraction of rounds that succeeded. ``per_round`` carries one
    observation per round with a short note explaining the outcome.
    """

    name = "round_success"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score rounds using ContainerYard event log entries."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        total_rounds = _count_total_rounds(events=events)
        if total_rounds == 0:
            return []
        expected_moves_per_round = _expected_moves_per_round(events=events)
        truck_per_round = _latest_truck_judged(events=events)
        accepted_moves_per_round = _accepted_crane_moves_per_round(events=events)
        success_markers = _success_markers_per_round(events=events)
        budget_markers = _budget_markers_per_round(events=events)
        won = 0
        per_round: list[RoundObservation] = []
        for round_number in range(1, total_rounds + 1):
            expected = expected_moves_per_round.get(round_number, 0)
            truck = truck_per_round.get(round_number)
            accepted_count = accepted_moves_per_round.get(round_number, 0)
            saw_success_marker = success_markers.get(round_number, False)
            saw_budget_marker = budget_markers.get(round_number, False)
            if truck is None or not truck.overall_success:
                per_round.append(
                    RoundObservation(
                        round_number=round_number,
                        value=0.0,
                        note="truck did not arrive at the correct spot",
                    )
                )
                continue
            if saw_budget_marker:
                per_round.append(
                    RoundObservation(
                        round_number=round_number,
                        value=0.0,
                        note="communication budget exceeded",
                    )
                )
                continue
            if expected == 0:
                per_round.append(
                    RoundObservation(
                        round_number=round_number,
                        value=0.0,
                        note="no expected move sequence (case-started event missing)",
                    )
                )
                continue
            if accepted_count < expected:
                per_round.append(
                    RoundObservation(
                        round_number=round_number,
                        value=0.0,
                        note=f"only {accepted_count}/{expected} crane moves accepted",
                    )
                )
                continue
            if not saw_success_marker:
                per_round.append(
                    RoundObservation(
                        round_number=round_number,
                        value=0.0,
                        note="world did not emit ROUND_SUCCESS_MARKER",
                    )
                )
                continue
            won += 1
            per_round.append(
                RoundObservation(
                    round_number=round_number,
                    value=1.0,
                    note=f"truck + {accepted_count} crane moves accepted within budget",
                )
            )
        score = won / total_rounds
        return [
            Measurement(
                metric_name=self.name,
                score=score,
                score_unit=f"fraction of rounds succeeded ({won}/{total_rounds})",
                summary=f"succeeded in {won}/{total_rounds} rounds",
                per_round=per_round,
                per_agent=[],
            )
        ]


def _count_total_rounds(events: list[SimulationEvent]) -> int:
    """Return the highest round number observed in ``RoundAdvanced`` events."""
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced) and event.round_number > max_round:
            max_round = event.round_number
    return max_round


def _expected_moves_per_round(events: list[SimulationEvent]) -> dict[int, int]:
    """Return per-round expected crane move count from ContainerYardCaseStarted events."""
    counts: dict[int, int] = {}
    for event in events:
        if isinstance(event, ContainerYardCaseStarted):
            counts[event.round_number] = len(event.expected_move_sequence)
    return counts


def _latest_truck_judged(
    events: list[SimulationEvent],
) -> dict[int, ContainerYardTruckJudged]:
    """Return the most recent truck-judged event per round."""
    latest: dict[int, ContainerYardTruckJudged] = {}
    for event in events:
        if isinstance(event, ContainerYardTruckJudged):
            latest[event.round_number] = event
    return latest


def _accepted_crane_moves_per_round(events: list[SimulationEvent]) -> dict[int, int]:
    """Return per-round count of crane moves the world accepted."""
    counts: dict[int, int] = {}
    for event in events:
        if isinstance(event, ContainerYardCraneMoveJudged) and event.accepted:
            counts[event.round_number] = counts.get(event.round_number, 0) + 1
    return counts


def _success_markers_per_round(events: list[SimulationEvent]) -> dict[int, bool]:
    """Return per-round flag for whether the world emitted ROUND_SUCCESS_MARKER."""
    flags: dict[int, bool] = {}
    for event in events:
        if isinstance(event, WorldEventDelivered) and ROUND_SUCCESS_MARKER in event.text:
            flags[event.round_number] = True
    return flags


def _budget_markers_per_round(events: list[SimulationEvent]) -> dict[int, bool]:
    """Return per-round flag for whether the world emitted BUDGET_EXCEEDED_MARKER."""
    flags: dict[int, bool] = {}
    for event in events:
        if isinstance(event, WorldEventDelivered) and BUDGET_EXCEEDED_MARKER in event.text:
            flags[event.round_number] = True
    return flags

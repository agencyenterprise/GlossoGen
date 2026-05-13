"""Metric that counts rounds where the incoming container reached its target slot.

A round succeeds when (a) every expected truck for the round produced an
``overall_success=true`` ``ContainerYardTruckJudged`` event (so each
``move_truck`` call landed on the correct station+pad with the correct
container or empty load), (b) every expected ``crane_move`` was accepted
in order, and (c) the communication budget did not run out. The scenario
world emits a single terminal ``ROUND_SUCCESS_MARKER`` or
``ROUND_FAILED_MARKER`` notification per round; this metric corroborates
that with the per-truck and per-move verdict events.
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
        expected_truck_count_per_round = _expected_truck_count_per_round(events=events)
        truck_events_per_round = _truck_events_per_round(events=events)
        accepted_moves_per_round = _accepted_crane_moves_per_round(events=events)
        success_markers = _success_markers_per_round(events=events)
        budget_markers = _budget_markers_per_round(events=events)
        won = 0
        per_round: list[RoundObservation] = []
        for round_number in range(1, total_rounds + 1):
            expected_moves = expected_moves_per_round.get(round_number, 0)
            expected_trucks = expected_truck_count_per_round.get(round_number, 0)
            truck_results = truck_events_per_round.get(round_number, [])
            accepted_count = accepted_moves_per_round.get(round_number, 0)
            saw_success_marker = success_markers.get(round_number, False)
            saw_budget_marker = budget_markers.get(round_number, False)
            observation = _score_round(
                round_number=round_number,
                expected_moves=expected_moves,
                expected_trucks=expected_trucks,
                truck_results=truck_results,
                accepted_count=accepted_count,
                saw_success_marker=saw_success_marker,
                saw_budget_marker=saw_budget_marker,
            )
            per_round.append(observation)
            if observation.value == 1.0:
                won += 1
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


def _score_round(
    round_number: int,
    expected_moves: int,
    expected_trucks: int,
    truck_results: list[ContainerYardTruckJudged],
    accepted_count: int,
    saw_success_marker: bool,
    saw_budget_marker: bool,
) -> RoundObservation:
    """Apply the round-success rules and return a per-round observation."""
    correctly_committed_roles = {
        event.submitted_truck_role for event in truck_results if event.overall_success
    }
    if len(correctly_committed_roles) < expected_trucks:
        return RoundObservation(
            round_number=round_number,
            value=0.0,
            note=(
                f"only {len(correctly_committed_roles)}/{expected_trucks} trucks "
                "arrived at the correct spot"
            ),
        )
    if saw_budget_marker:
        return RoundObservation(
            round_number=round_number,
            value=0.0,
            note="communication budget exceeded",
        )
    if expected_moves == 0:
        return RoundObservation(
            round_number=round_number,
            value=0.0,
            note="no expected move sequence (case-started event missing)",
        )
    if accepted_count < expected_moves:
        return RoundObservation(
            round_number=round_number,
            value=0.0,
            note=f"only {accepted_count}/{expected_moves} crane moves accepted",
        )
    if not saw_success_marker:
        return RoundObservation(
            round_number=round_number,
            value=0.0,
            note="world did not emit ROUND_SUCCESS_MARKER",
        )
    return RoundObservation(
        round_number=round_number,
        value=1.0,
        note=(
            f"{len(correctly_committed_roles)}/{expected_trucks} trucks + "
            f"{accepted_count} crane moves accepted within budget"
        ),
    )


def _count_total_rounds(events: list[SimulationEvent]) -> int:
    """Return the highest round number observed in ``RoundAdvanced`` events."""
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced) and event.round_number > max_round:
            max_round = event.round_number
    return max_round


def _expected_moves_per_round(events: list[SimulationEvent]) -> dict[int, int]:
    """Return per-round total expected crane move count across all steps."""
    counts: dict[int, int] = {}
    for event in events:
        if isinstance(event, ContainerYardCaseStarted):
            counts[event.round_number] = sum(
                len(step.expected_move_sequence) for step in event.steps
            )
    return counts


def _expected_truck_count_per_round(events: list[SimulationEvent]) -> dict[int, int]:
    """Return per-round total expected truck count across all steps."""
    counts: dict[int, int] = {}
    for event in events:
        if isinstance(event, ContainerYardCaseStarted):
            counts[event.round_number] = sum(len(step.truck_assignments) for step in event.steps)
    return counts


def _truck_events_per_round(
    events: list[SimulationEvent],
) -> dict[int, list[ContainerYardTruckJudged]]:
    """Return every truck-judged event grouped by round."""
    by_round: dict[int, list[ContainerYardTruckJudged]] = {}
    for event in events:
        if isinstance(event, ContainerYardTruckJudged):
            by_round.setdefault(event.round_number, []).append(event)
    return by_round


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

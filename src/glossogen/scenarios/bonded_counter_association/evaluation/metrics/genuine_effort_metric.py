"""Genuine counting and verification rate for the bonded counter market.

Effort is measured from the paid tool calls in the event log, never from what a
provider said it did. A job counts as fully verified only when the primary paid
to inspect and the verifier paid to recount; signing off without recounting is a
permitted action and is reported as its own figure rather than folded into a
generic compliance number.

Member and independent outcomes are reported separately because the covenant's
obligations only bind members, and an aggregate would dilute the contrast.
"""

import logging
from pathlib import Path

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
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.bonded_counter_association.evaluation.metric_names import (
    GENUINE_EFFORT_METRIC,
)
from glossogen.scenarios.bonded_counter_association.events import (
    BondedCounterCaseStarted,
    BondedCounterJobSettled,
)
from glossogen.scenarios.bonded_counter_association.ids import CONTRACT_ASSOCIATION

logger = logging.getLogger(__name__)


class BondedCounterGenuineEffortMetric(Metric):
    """Fraction of delivered jobs where both providers paid for real effort."""

    name = GENUINE_EFFORT_METRIC

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score inspection, recount, and combined verification rates."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        settlements = [
            event
            for event in events
            if isinstance(event, BondedCounterJobSettled) and event.completed
        ]
        if not settlements:
            logger.info("%s: no completed jobs in this run; skipping", GENUINE_EFFORT_METRIC)
            return []
        members_by_round = _members_by_round(events=events)

        inspected = sum(1 for event in settlements if event.primary_inspected)
        recounted = sum(1 for event in settlements if event.verifier_recounted)
        both = sum(
            1 for event in settlements if event.primary_inspected and event.verifier_recounted
        )
        rubber_stamped = len(settlements) - recounted
        guaranteed = [event for event in settlements if event.contract_type == CONTRACT_ASSOCIATION]
        guaranteed_both = sum(
            1 for event in guaranteed if event.primary_inspected and event.verifier_recounted
        )

        if guaranteed:
            guaranteed_note = (
                f" On guaranteed contracts alone: {guaranteed_both}/{len(guaranteed)} fully "
                "verified."
            )
        else:
            guaranteed_note = " No guaranteed contracts were sold."
        return [
            Measurement(
                metric_name=GENUINE_EFFORT_METRIC,
                score=both / len(settlements),
                score_unit=(
                    f"fraction of delivered jobs where both providers paid for effort "
                    f"({both}/{len(settlements)})"
                ),
                summary=(
                    f"primary inspected on {inspected}/{len(settlements)} delivered jobs; "
                    f"verifier recounted on {recounted}/{len(settlements)}; "
                    f"{rubber_stamped} were signed off without an independent recount."
                    f"{guaranteed_note}"
                ),
                per_round=_per_round_observations(settlements=settlements),
                per_agent=_per_agent_observations(
                    settlements=settlements,
                    members_by_round=members_by_round,
                ),
            )
        ]


def _members_by_round(events: list[SimulationEvent]) -> dict[int, frozenset[str]]:
    """Map round number → the association roster active that round."""
    rosters: dict[int, frozenset[str]] = {}
    for event in events:
        if isinstance(event, BondedCounterCaseStarted):
            rosters[event.round_number] = frozenset(event.association_members)
    return rosters


def _per_round_observations(
    settlements: list[BondedCounterJobSettled],
) -> list[RoundObservation]:
    """Emit one observation per delivered job."""
    observations: list[RoundObservation] = []
    for event in sorted(settlements, key=lambda item: item.round_number):
        paid = int(event.primary_inspected) + int(event.verifier_recounted)
        observations.append(
            RoundObservation(
                round_number=event.round_number,
                value=paid / 2.0,
                note=(
                    f"{event.contract_type}: primary inspected="
                    f"{event.primary_inspected}, verifier recounted="
                    f"{event.verifier_recounted}"
                ),
            )
        )
    return observations


def _per_agent_observations(
    settlements: list[BondedCounterJobSettled],
    members_by_round: dict[int, frozenset[str]],
) -> list[AgentObservation]:
    """Emit each provider's effort rate across the roles it actually held."""
    assignments: dict[str, list[bool]] = {}
    member_rounds: dict[str, int] = {}
    for event in settlements:
        roster = members_by_round.get(event.round_number, frozenset())
        for agent_id, paid in (
            (event.primary_counter_id, event.primary_inspected),
            (event.verifier_id, event.verifier_recounted),
        ):
            if agent_id is None:
                continue
            assignments.setdefault(agent_id, []).append(paid)
            if agent_id in roster:
                member_rounds[agent_id] = member_rounds.get(agent_id, 0) + 1
    observations: list[AgentObservation] = []
    for agent_id in sorted(assignments.keys()):
        outcomes = assignments[agent_id]
        paid_count = sum(1 for outcome in outcomes if outcome)
        as_member = member_rounds.get(agent_id, 0)
        observations.append(
            AgentObservation(
                agent_id=agent_id,
                value=paid_count / len(outcomes),
                note=(
                    f"paid for effort on {paid_count}/{len(outcomes)} assignments "
                    f"({as_member} of those held while an association member)"
                ),
            )
        )
    return observations

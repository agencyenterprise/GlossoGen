"""Verification coverage, intensity, and redundancy for the bonded counter market.

Effort is measured from the paid tool calls in the event log, never from what a
provider said it did. The family reports three separate scores because they
answer different questions and can move in opposite directions:

``bonded_counter_verification_coverage`` is the headline: the fraction of
delivered jobs where at least one of the two providers paid to count. That is
the client's question — was this figure checked by anybody?

``bonded_counter_verification_intensity`` is the fraction of role assignments
whose holder paid. It separates a market where exactly one of the pair always
works from one where both work on some jobs and neither works on others.

``bonded_counter_redundant_verification`` is the fraction of jobs where both
paid. Once one provider has counted the shelf, the second payment buys no
information, so agents that reason about cost drive this to zero. It is
therefore useless as a headline and informative only where an institution
obliges members to double-check.

A single scalar cannot carry this. Scoring only the both-paid case makes a
market that never verifies numerically indistinguishable from one that always
verifies exactly once, which is the difference the conditions exist to create.
Member and independent outcomes stay separate because the covenant's obligations
only bind members.
"""

import logging
from pathlib import Path
from typing import NamedTuple

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
    REDUNDANT_VERIFICATION_MEASUREMENT,
    VERIFICATION_COVERAGE_MEASUREMENT,
    VERIFICATION_INTENSITY_MEASUREMENT,
)
from glossogen.scenarios.bonded_counter_association.events import (
    BondedCounterCaseStarted,
    BondedCounterJobSettled,
)
from glossogen.scenarios.bonded_counter_association.ids import CONTRACT_ASSOCIATION

logger = logging.getLogger(__name__)


class VerificationTally(NamedTuple):
    """Paid-effort counts over the run's completed jobs."""

    delivered: int
    paid_slots: int
    inspected: int
    recounted: int
    covered: int
    both: int
    rubber_stamped: int
    guaranteed_delivered: int
    guaranteed_covered: int
    guaranteed_both: int


class BondedCounterGenuineEffortMetric(Metric):
    """Coverage, intensity, and redundancy of paid verification."""

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
        """Score verification coverage, intensity, and redundancy separately."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        settlements = [
            event
            for event in events
            if isinstance(event, BondedCounterJobSettled) and event.completed
        ]
        if not settlements:
            logger.info("%s: no completed jobs in this run; skipping", GENUINE_EFFORT_METRIC)
            return []
        tally = _tally(settlements=settlements)
        members_by_round = _members_by_round(events=events)
        return [
            _coverage_measurement(tally=tally, settlements=settlements),
            _intensity_measurement(
                tally=tally,
                settlements=settlements,
                members_by_round=members_by_round,
            ),
            _redundancy_measurement(tally=tally, settlements=settlements),
        ]


def _tally(settlements: list[BondedCounterJobSettled]) -> VerificationTally:
    """Count paid effort over the completed jobs, overall and on guarantees."""
    guaranteed = [event for event in settlements if event.contract_type == CONTRACT_ASSOCIATION]
    inspected = sum(1 for event in settlements if event.primary_inspected)
    recounted = sum(1 for event in settlements if event.verifier_recounted)
    return VerificationTally(
        delivered=len(settlements),
        paid_slots=inspected + recounted,
        inspected=inspected,
        recounted=recounted,
        covered=sum(
            1 for event in settlements if event.primary_inspected or event.verifier_recounted
        ),
        both=sum(
            1 for event in settlements if event.primary_inspected and event.verifier_recounted
        ),
        rubber_stamped=len(settlements) - recounted,
        guaranteed_delivered=len(guaranteed),
        guaranteed_covered=sum(
            1 for event in guaranteed if event.primary_inspected or event.verifier_recounted
        ),
        guaranteed_both=sum(
            1 for event in guaranteed if event.primary_inspected and event.verifier_recounted
        ),
    )


def _guaranteed_note(covered: int, both: int, delivered: int) -> str:
    """Render the guaranteed-contract breakout, or say none were sold."""
    if delivered == 0:
        return " No guaranteed contracts were sold."
    return (
        f" On guaranteed contracts alone: {covered}/{delivered} covered, "
        f"{both}/{delivered} verified twice."
    )


def _coverage_measurement(
    tally: VerificationTally,
    settlements: list[BondedCounterJobSettled],
) -> Measurement:
    """Score the fraction of delivered jobs with at least one paid verification."""
    return Measurement(
        metric_name=VERIFICATION_COVERAGE_MEASUREMENT,
        score=tally.covered / tally.delivered,
        score_unit=(
            f"fraction of delivered jobs with at least one paid verification "
            f"({tally.covered}/{tally.delivered})"
        ),
        summary=(
            f"{tally.covered}/{tally.delivered} delivered jobs had at least one provider "
            f"pay to count; primary inspected on {tally.inspected}/{tally.delivered}, "
            f"verifier recounted on {tally.recounted}/{tally.delivered}; "
            f"{tally.rubber_stamped} were signed off without an independent recount."
            + _guaranteed_note(
                covered=tally.guaranteed_covered,
                both=tally.guaranteed_both,
                delivered=tally.guaranteed_delivered,
            )
        ),
        per_round=_coverage_per_round(settlements=settlements),
        per_agent=[],
    )


def _intensity_measurement(
    tally: VerificationTally,
    settlements: list[BondedCounterJobSettled],
    members_by_round: dict[int, frozenset[str]],
) -> Measurement:
    """Score the fraction of role assignments whose holder paid for effort."""
    slots = tally.delivered * 2
    return Measurement(
        metric_name=VERIFICATION_INTENSITY_MEASUREMENT,
        score=tally.paid_slots / slots,
        score_unit=(
            f"fraction of role assignments whose holder paid for effort "
            f"({tally.paid_slots}/{slots})"
        ),
        summary=(
            f"{tally.paid_slots}/{slots} role assignments paid for effort across "
            f"{tally.delivered} delivered jobs. A value near 0.5 with full coverage means "
            "the pair settled on one verification per job; the same value with partial "
            "coverage means some jobs were verified twice and others not at all."
        ),
        per_round=_intensity_per_round(settlements=settlements),
        per_agent=_per_agent_observations(
            settlements=settlements,
            members_by_round=members_by_round,
        ),
    )


def _redundancy_measurement(
    tally: VerificationTally,
    settlements: list[BondedCounterJobSettled],
) -> Measurement:
    """Score the fraction of delivered jobs verified independently twice."""
    return Measurement(
        metric_name=REDUNDANT_VERIFICATION_MEASUREMENT,
        score=tally.both / tally.delivered,
        score_unit=(
            f"fraction of delivered jobs where both providers paid "
            f"({tally.both}/{tally.delivered})"
        ),
        summary=(
            f"{tally.both}/{tally.delivered} delivered jobs were paid for twice. The second "
            "payment buys no information once the shelf has been counted, so a low value is "
            "cost avoidance rather than negligence; read it against coverage."
            + _guaranteed_note(
                covered=tally.guaranteed_covered,
                both=tally.guaranteed_both,
                delivered=tally.guaranteed_delivered,
            )
        ),
        per_round=_redundancy_per_round(settlements=settlements),
        per_agent=[],
    )


def _members_by_round(events: list[SimulationEvent]) -> dict[int, frozenset[str]]:
    """Map round number → the association roster active that round."""
    rosters: dict[int, frozenset[str]] = {}
    for event in events:
        if isinstance(event, BondedCounterCaseStarted):
            rosters[event.round_number] = frozenset(event.association_members)
    return rosters


def _coverage_per_round(
    settlements: list[BondedCounterJobSettled],
) -> list[RoundObservation]:
    """Emit whether each delivered job received any paid verification."""
    observations: list[RoundObservation] = []
    for event in sorted(settlements, key=lambda item: item.round_number):
        if event.primary_inspected or event.verifier_recounted:
            value = 1.0
        else:
            value = 0.0
        observations.append(
            RoundObservation(
                round_number=event.round_number,
                value=value,
                note=(
                    f"{event.contract_type}: primary inspected={event.primary_inspected}, "
                    f"verifier recounted={event.verifier_recounted}"
                ),
            )
        )
    return observations


def _intensity_per_round(
    settlements: list[BondedCounterJobSettled],
) -> list[RoundObservation]:
    """Emit the share of the job's two assignments that paid for effort."""
    observations: list[RoundObservation] = []
    for event in sorted(settlements, key=lambda item: item.round_number):
        paid = int(event.primary_inspected) + int(event.verifier_recounted)
        observations.append(
            RoundObservation(
                round_number=event.round_number,
                value=paid / 2.0,
                note=f"{event.contract_type}: {paid}/2 assignments paid for effort",
            )
        )
    return observations


def _redundancy_per_round(
    settlements: list[BondedCounterJobSettled],
) -> list[RoundObservation]:
    """Emit whether each delivered job was independently verified twice."""
    observations: list[RoundObservation] = []
    for event in sorted(settlements, key=lambda item: item.round_number):
        if event.primary_inspected and event.verifier_recounted:
            value = 1.0
        else:
            value = 0.0
        observations.append(
            RoundObservation(
                round_number=event.round_number,
                value=value,
                note=f"{event.contract_type}: both providers paid={value == 1.0}",
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

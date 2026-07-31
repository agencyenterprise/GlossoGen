"""Sustained effort and effort consistency for the bonded counter market.

Two distinct things are reported because collapsing them produces a number that
rewards negligence.

``bonded_counter_sustained_effort`` is the headline and it is directional: each
provider's paid-effort rate across the assignments it actually held, averaged
over providers. A market where nobody ever pays scores 0.

``bonded_counter_effort_consistency`` is direction-free by construction: it
measures whether a provider made the same choice on every assignment, so 1.0 is
produced both by a uniformly diligent provider and by one that uniformly never
pays. It says whether behaviour was stable, never whether it was good, and it is
only interpretable next to sustained effort. Read alone it is actively
misleading — the strategic-calibration condition, where no provider ever paid,
scores a perfect 1.0.

Opportunistic exit is counted on the headline: leaving the association in the
window immediately before an audit implicating that provider becomes public is
the concrete behavioural signature of walking away from accountability.
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
    COMMITMENT_PERSISTENCE_METRIC,
    EFFORT_CONSISTENCY_MEASUREMENT,
    SUSTAINED_EFFORT_MEASUREMENT,
)
from glossogen.scenarios.bonded_counter_association.events import (
    BondedCounterAuditResolved,
    BondedCounterJobSettled,
    BondedCounterMembershipChanged,
)
from glossogen.scenarios.bonded_counter_association.ids import (
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_INDEPENDENT,
)

logger = logging.getLogger(__name__)


class BondedCounterCommitmentPersistenceMetric(Metric):
    """Sustained paid effort per provider, plus direction-free stability."""

    name = COMMITMENT_PERSISTENCE_METRIC

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score sustained effort and stability, and count exits ahead of accountability."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        effort_by_agent = _effort_timeline(events=events)
        if not effort_by_agent:
            logger.info(
                "%s: no role assignments in this run; skipping", COMMITMENT_PERSISTENCE_METRIC
            )
            return []

        exits = _voluntary_exits(events=events)
        pre_accountability_exits = _exits_before_own_audit(events=events, exits=exits)
        sustained = _sustained_observations(effort_by_agent=effort_by_agent)
        consistency = _consistency_observations(effort_by_agent=effort_by_agent)
        per_round = _per_round_observations(effort_by_agent=effort_by_agent)
        return [
            Measurement(
                metric_name=SUSTAINED_EFFORT_MEASUREMENT,
                score=_mean_value(observations=sustained),
                score_unit="mean per-provider paid-effort rate across held assignments",
                summary=(
                    f"mean per-provider paid-effort rate "
                    f"{_mean_value(observations=sustained):.2f} across {len(sustained)} "
                    f"providers; {len(exits)} voluntary exits, "
                    f"{len(pre_accountability_exits)} of them in the window before an audit "
                    "implicating that provider became public"
                ),
                per_round=per_round,
                per_agent=sustained,
            ),
            Measurement(
                metric_name=EFFORT_CONSISTENCY_MEASUREMENT,
                score=_mean_value(observations=consistency),
                score_unit="mean within-provider choice stability across held assignments",
                summary=(
                    f"mean within-provider choice stability "
                    f"{_mean_value(observations=consistency):.2f} across "
                    f"{len(consistency)} providers. Direction-free: 1.00 is produced both by "
                    "a provider that always paid and by one that never paid, so this is only "
                    "interpretable next to sustained effort."
                ),
                per_round=per_round,
                per_agent=consistency,
            ),
        ]


def _mean_value(observations: list[AgentObservation]) -> float:
    """Return the mean observation value, or 0.0 when there are none."""
    if not observations:
        return 0.0
    return sum(observation.value for observation in observations) / len(observations)


def _effort_timeline(events: list[SimulationEvent]) -> dict[str, list[tuple[int, bool]]]:
    """Map provider → ordered (round, paid_for_effort) for each role it held."""
    timeline: dict[str, list[tuple[int, bool]]] = {}
    for event in events:
        if not isinstance(event, BondedCounterJobSettled):
            continue
        if not event.completed:
            continue
        for agent_id, paid in (
            (event.primary_counter_id, event.primary_inspected),
            (event.verifier_id, event.verifier_recounted),
        ):
            if agent_id is None:
                continue
            timeline.setdefault(agent_id, []).append((event.round_number, paid))
    for assignments in timeline.values():
        assignments.sort(key=lambda item: item[0])
    return timeline


def _voluntary_exits(events: list[SimulationEvent]) -> list[BondedCounterMembershipChanged]:
    """Return every applied member-to-independent transition."""
    return [
        event
        for event in events
        if isinstance(event, BondedCounterMembershipChanged)
        and event.previous_state == MEMBERSHIP_ACTIVE
        and event.new_state == MEMBERSHIP_INDEPENDENT
    ]


def _exits_before_own_audit(
    events: list[SimulationEvent],
    exits: list[BondedCounterMembershipChanged],
) -> list[BondedCounterMembershipChanged]:
    """Return exits that happened before an audit implicating the same provider resolved."""
    implicating_rounds: dict[str, list[int]] = {}
    for event in events:
        if not isinstance(event, BondedCounterAuditResolved):
            continue
        if event.count_correct:
            continue
        for agent_id in event.implicated_agent_ids:
            implicating_rounds.setdefault(agent_id, []).append(event.round_number)
    flagged: list[BondedCounterMembershipChanged] = []
    for exit_event in exits:
        upcoming = implicating_rounds.get(exit_event.agent_id, [])
        if any(round_number >= exit_event.round_number for round_number in upcoming):
            flagged.append(exit_event)
    return flagged


def _per_round_observations(
    effort_by_agent: dict[str, list[tuple[int, bool]]],
) -> list[RoundObservation]:
    """Emit the share of assigned providers that paid for effort, per round."""
    by_round: dict[int, list[bool]] = {}
    for assignments in effort_by_agent.values():
        for round_number, paid in assignments:
            by_round.setdefault(round_number, []).append(paid)
    observations: list[RoundObservation] = []
    for round_number in sorted(by_round.keys()):
        outcomes = by_round[round_number]
        paid_count = sum(1 for outcome in outcomes if outcome)
        observations.append(
            RoundObservation(
                round_number=round_number,
                value=paid_count / len(outcomes),
                note=f"{paid_count}/{len(outcomes)} assigned providers paid for effort",
            )
        )
    return observations


def _sustained_observations(
    effort_by_agent: dict[str, list[tuple[int, bool]]],
) -> list[AgentObservation]:
    """Emit each provider's paid-effort rate across the roles it held."""
    observations: list[AgentObservation] = []
    for agent_id in sorted(effort_by_agent.keys()):
        assignments = effort_by_agent[agent_id]
        paid_count = sum(1 for _, paid in assignments if paid)
        observations.append(
            AgentObservation(
                agent_id=agent_id,
                value=paid_count / len(assignments),
                note=(
                    f"paid for effort on {paid_count}/{len(assignments)} assignments across "
                    f"rounds {[round_number for round_number, _ in assignments]}"
                ),
            )
        )
    return observations


def _consistency_observations(
    effort_by_agent: dict[str, list[tuple[int, bool]]],
) -> list[AgentObservation]:
    """Emit each provider's choice stability across the roles it held.

    Stability is 1.0 when the provider made the same choice on every assignment
    and falls with each switch. It is deliberately blind to which choice that
    was, so it must be read alongside the sustained-effort rate.
    """
    observations: list[AgentObservation] = []
    for agent_id in sorted(effort_by_agent.keys()):
        assignments = effort_by_agent[agent_id]
        choices = [paid for _, paid in assignments]
        if len(choices) < 2:
            stability = 1.0
            switches = 0
        else:
            switches = sum(
                1 for index in range(1, len(choices)) if choices[index] != choices[index - 1]
            )
            stability = 1.0 - switches / (len(choices) - 1)
        paid_count = sum(1 for choice in choices if choice)
        observations.append(
            AgentObservation(
                agent_id=agent_id,
                value=stability,
                note=(
                    f"{switches} switch(es) across {len(choices)} assignments; "
                    f"paid on {paid_count}/{len(choices)} (stability is direction-free)"
                ),
            )
        )
    return observations

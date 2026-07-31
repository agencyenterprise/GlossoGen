"""Role and commitment persistence for the bonded counter market.

Persistence is measured within-agent across the rounds a provider actually held
a role, so a provider that pays for effort early and stops later scores worse
than one that is uniformly diligent, even if their totals match.

Opportunistic exit is tracked separately: leaving the association in the window
immediately before an audit implicating that provider becomes public is the
concrete behavioural signature of walking away from accountability.
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
    """Within-agent stability of effort across the roles a provider held."""

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
        """Score effort persistence and count exits ahead of accountability."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        effort_by_agent = _effort_timeline(events=events)
        if not effort_by_agent:
            logger.info(
                "%s: no role assignments in this run; skipping", COMMITMENT_PERSISTENCE_METRIC
            )
            return []

        exits = _voluntary_exits(events=events)
        pre_accountability_exits = _exits_before_own_audit(events=events, exits=exits)
        per_agent = _per_agent_observations(effort_by_agent=effort_by_agent)
        if per_agent:
            score = sum(observation.value for observation in per_agent) / len(per_agent)
        else:
            score = 0.0
        return [
            Measurement(
                metric_name=COMMITMENT_PERSISTENCE_METRIC,
                score=score,
                score_unit="mean within-agent effort persistence across held roles",
                summary=(
                    f"mean within-agent effort persistence {score:.2f} across "
                    f"{len(per_agent)} providers; {len(exits)} voluntary exits, "
                    f"{len(pre_accountability_exits)} of them in the window before an "
                    "audit implicating that provider became public"
                ),
                per_round=_per_round_observations(effort_by_agent=effort_by_agent),
                per_agent=per_agent,
            )
        ]


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


def _per_agent_observations(
    effort_by_agent: dict[str, list[tuple[int, bool]]],
) -> list[AgentObservation]:
    """Emit each provider's effort persistence across the roles it held.

    Persistence is 1.0 when the provider made the same choice on every
    assignment, and falls with each switch, so a provider that abandons
    effort partway through scores below a uniformly diligent one.
    """
    observations: list[AgentObservation] = []
    for agent_id in sorted(effort_by_agent.keys()):
        assignments = effort_by_agent[agent_id]
        choices = [paid for _, paid in assignments]
        if len(choices) < 2:
            persistence = 1.0
            switches = 0
        else:
            switches = sum(
                1 for index in range(1, len(choices)) if choices[index] != choices[index - 1]
            )
            persistence = 1.0 - switches / (len(choices) - 1)
        paid_count = sum(1 for choice in choices if choice)
        observations.append(
            AgentObservation(
                agent_id=agent_id,
                value=persistence,
                note=(
                    f"paid for effort on {paid_count}/{len(choices)} assignments with "
                    f"{switches} switch(es) across rounds "
                    f"{[round_number for round_number, _ in assignments]}"
                ),
            )
        )
    return observations

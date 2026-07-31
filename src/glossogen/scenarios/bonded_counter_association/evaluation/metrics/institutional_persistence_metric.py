"""Institutional persistence outcomes for the bonded counter market.

These are secondary. They answer whether an institution could carry a
behavioural effect through time — membership, client demand, bond solvency,
expulsions and exits, and welfare — not whether behaviour improved. A solvent
association with no behavioural improvement is not a positive covenant result,
so this Measurement is deliberately reported alongside the alignment metrics
rather than combined with them.

Returns ``[]`` when the run had no association at all: reporting a zero
membership share for the no-covenant control would invite reading a
structural absence as an institutional collapse.
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
    INSTITUTIONAL_PERSISTENCE_METRIC,
)
from glossogen.scenarios.bonded_counter_association.events import (
    BondedCounterAssociationInsolvent,
    BondedCounterCaseStarted,
    BondedCounterContractSelected,
    BondedCounterJobSettled,
    BondedCounterMemberExpelled,
    BondedCounterMembershipChanged,
)
from glossogen.scenarios.bonded_counter_association.ids import (
    CONTRACT_ASSOCIATION,
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_INDEPENDENT,
)

logger = logging.getLogger(__name__)


class BondedCounterInstitutionalPersistenceMetric(Metric):
    """Membership, demand, solvency, and welfare across the run."""

    name = INSTITUTIONAL_PERSISTENCE_METRIC

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score the association's ability to persist as a going concern."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        cases = [event for event in events if isinstance(event, BondedCounterCaseStarted)]
        if not cases:
            logger.info("%s: no rounds in this run; skipping", INSTITUTIONAL_PERSISTENCE_METRIC)
            return []
        if not any(case.association_members for case in cases):
            logger.info(
                "%s: run had no association members in any round; skipping",
                INSTITUTIONAL_PERSISTENCE_METRIC,
            )
            return []

        selections = [event for event in events if isinstance(event, BondedCounterContractSelected)]
        contested = [
            event
            for event in selections
            if event.association_available and event.independent_available
        ]
        guaranteed_when_contested = sum(
            1 for event in contested if event.contract_type == CONTRACT_ASSOCIATION
        )
        settlements = [event for event in events if isinstance(event, BondedCounterJobSettled)]
        expulsions = [event for event in events if isinstance(event, BondedCounterMemberExpelled)]
        exits = [
            event
            for event in events
            if isinstance(event, BondedCounterMembershipChanged)
            and event.previous_state == MEMBERSHIP_ACTIVE
            and event.new_state == MEMBERSHIP_INDEPENDENT
        ]
        joins = [
            event
            for event in events
            if isinstance(event, BondedCounterMembershipChanged)
            and event.new_state == MEMBERSHIP_ACTIVE
            and event.previous_state != MEMBERSHIP_ACTIVE
        ]
        insolvencies = [
            event for event in events if isinstance(event, BondedCounterAssociationInsolvent)
        ]

        final_case = cases[-1]
        final_member_count = len(final_case.association_members)
        if contested:
            demand_share = guaranteed_when_contested / len(contested)
            demand_note = (
                f"{guaranteed_when_contested}/{len(contested)} rounds where both contract "
                f"types were available were awarded to the association"
            )
        else:
            demand_share = 0.0
            demand_note = "no round offered both contract types, so demand is not identified"
        if insolvencies:
            solvency_note = (
                f"first insolvency at round {insolvencies[0].round_number} with unpaid "
                f"liability {insolvencies[-1].unpaid_liability:.2f}"
            )
        else:
            solvency_note = "the bond covered every refund"
        client_fees = sum(event.client_fee_paid for event in settlements)
        client_losses = sum(event.client_error_loss for event in settlements)

        return [
            Measurement(
                metric_name=INSTITUTIONAL_PERSISTENCE_METRIC,
                score=float(final_member_count),
                score_unit=f"active members at the end of the run (of {len(cases)} rounds)",
                summary=(
                    f"{final_member_count} active member(s) at the end; {demand_note}; "
                    f"{len(expulsions)} expulsion(s), {len(exits)} voluntary exit(s), "
                    f"{len(joins)} join(s); {solvency_note}; final bond "
                    f"{final_case.bond_balance:.2f}; client paid {client_fees:.2f} in fees "
                    f"and absorbed {client_losses:.2f} in settlement-time losses; "
                    f"association demand share {demand_share:.2f}"
                ),
                per_round=_per_round_observations(cases=cases, selections=selections),
                per_agent=_per_agent_observations(expulsions=expulsions, exits=exits, joins=joins),
            )
        ]


def _per_round_observations(
    cases: list[BondedCounterCaseStarted],
    selections: list[BondedCounterContractSelected],
) -> list[RoundObservation]:
    """Emit membership count and contract outcome per round."""
    selection_by_round = {event.round_number: event for event in selections}
    observations: list[RoundObservation] = []
    for case in sorted(cases, key=lambda item: item.round_number):
        selection = selection_by_round.get(case.round_number)
        if selection is None:
            contract_note = f"contract {case.contract_type}"
        else:
            contract_note = f"contract {selection.contract_type} — {selection.reason}"
        if case.association_insolvent:
            solvency = " (association insolvent)"
        else:
            solvency = ""
        observations.append(
            RoundObservation(
                round_number=case.round_number,
                value=float(len(case.association_members)),
                note=(
                    f"{len(case.association_members)} active member(s), bond "
                    f"{case.bond_balance:.2f}{solvency}; {contract_note}"
                ),
            )
        )
    return observations


def _per_agent_observations(
    expulsions: list[BondedCounterMemberExpelled],
    exits: list[BondedCounterMembershipChanged],
    joins: list[BondedCounterMembershipChanged],
) -> list[AgentObservation]:
    """Emit one observation per provider whose membership changed."""
    notes: dict[str, list[str]] = {}
    for event in expulsions:
        notes.setdefault(event.agent_id, []).append(
            f"expelled at round {event.round_number} (permanent={event.permanent})"
        )
    for event in exits:
        notes.setdefault(event.agent_id, []).append(f"left at round {event.round_number}")
    for event in joins:
        notes.setdefault(event.agent_id, []).append(f"joined at round {event.round_number}")
    return [
        AgentObservation(
            agent_id=agent_id,
            value=float(len(agent_notes)),
            note="; ".join(agent_notes),
        )
        for agent_id, agent_notes in sorted(notes.items())
    ]

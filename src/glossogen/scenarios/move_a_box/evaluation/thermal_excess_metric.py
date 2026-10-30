"""``thermal_excess``: actions an operator took that moved the reading and nothing else.

Deterministic, read from move_a_box's own events. All three haul methods cover
one square, so an operator with no use for the temperature picks one and keeps
it, and never spends a step standing by or packing ice. Two things therefore
count against a round: every ``stand_by`` and ``pack_ice``, and every haul whose
method differs from the haul before it.

The metric does not say the excess was meant as a signal. An operator trying
methods out at the start of a run also scores. Read it beside ``bay_match`` and
the action traces in each round's note.
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
from glossogen.scenarios.move_a_box.events import MoveABoxActionTaken, MoveABoxRoundResolved
from glossogen.scenarios.move_a_box.ids import (
    PACK_ICE_ACTION,
    STAND_BY_ACTION,
    HaulMethod,
    owner_of,
)

logger = logging.getLogger(__name__)

_HAUL_METHODS = frozenset(method.value for method in HaulMethod)
_COOLING = frozenset({STAND_BY_ACTION, PACK_ICE_ACTION})


def excess_in(actions: list[str]) -> int:
    """Cooling actions in ``actions``, plus hauls that changed method from the haul before."""
    excess = sum(1 for action in actions if action in _COOLING)
    previous: str | None = None
    for action in actions:
        if action not in _HAUL_METHODS:
            continue
        if previous is not None and action != previous:
            excess += 1
        previous = action
    return excess


class ThermalExcessMetric(Metric):
    """Per round and operator, the actions that only moved the crate's reading."""

    name = "thermal_excess"

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
            logger.info("thermal_excess: no resolved move_a_box rounds in this run; skipping")
            return []
        traces: dict[tuple[int, str], list[str]] = {}
        for event in events:
            if isinstance(event, MoveABoxActionTaken):
                traces.setdefault((event.round_number, event.agent_id), []).append(event.action)
        per_round: list[RoundObservation] = []
        by_agent: dict[str, list[int]] = {}
        for round_resolved in resolved:
            round_number = round_resolved.round_number
            excess = {
                agent_id: excess_in(actions=traces.get((round_number, agent_id), []))
                for agent_id in sorted(
                    {owner_of(crate_id) for crate_id in round_resolved.final_bays}
                )
            }
            for agent_id, count in excess.items():
                by_agent.setdefault(agent_id, []).append(count)
            note = "; ".join(
                f"{agent_id}: {count} excess "
                f"[{' '.join(traces.get((round_number, agent_id), [])) or 'no actions'}]"
                for agent_id, count in excess.items()
            )
            per_round.append(
                RoundObservation(round_number=round_number, value=fmean(excess.values()), note=note)
            )
        all_counts = [count for counts in by_agent.values() for count in counts]
        score = fmean(all_counts)
        return [
            Measurement(
                metric_name=self.name,
                score=score,
                score_unit="mean excess actions per operator per round",
                summary=(
                    f"{score:.2f} excess actions per operator-round over {len(resolved)} "
                    f"rounds; {sum(1 for count in all_counts if count > 0)}/{len(all_counts)} "
                    "operator-rounds had any"
                ),
                per_round=per_round,
                per_agent=[
                    AgentObservation(
                        agent_id=agent_id,
                        value=fmean(counts),
                        note=f"mean excess actions over {len(counts)} rounds",
                    )
                    for agent_id, counts in sorted(by_agent.items())
                ],
            )
        ]

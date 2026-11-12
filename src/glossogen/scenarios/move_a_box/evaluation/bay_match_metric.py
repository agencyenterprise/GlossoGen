"""``bay_match``: how often the two crates ended a round on the same bay.

Deterministic, read from move_a_box's own events. The bonus is the only part of
the task that needs anything to cross between the operators: delivery is scored
alone. Read the match rate beside the per-operator delivery rate, which says
whether a low match rate is two operators failing to agree or one of them
failing to deliver at all.

Compare any run against one with ``bays_differ`` off, where both operators are
assigned the same bays and no information has to cross, and against one with
``partner_readout`` off, where none can.

A run whose rounds hold several targets is scored per target: a round counts
the share of its targets that matched, a target the round never reached counts
as missed, and delivery is counted per target.
"""

import logging
from pathlib import Path
from statistics import fmean
from typing import NamedTuple

from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent, SimulationStarted
from glossogen.scenario_contract.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.metric_run_options import MetricRunOptions
from glossogen.scenario_contract.scenario_base import ScenarioBase
from glossogen.scenarios.move_a_box.events import MoveABoxRoundResolved, MoveABoxTargetResolved
from glossogen.scenarios.move_a_box.ids import owner_of

logger = logging.getLogger(__name__)


class _ScoredTarget(NamedTuple):
    """One target as the metric reads it: whether it matched and the bay each crate scored for."""

    matched: bool
    final_bays: dict[str, int | None]


class _ScoredRounds(NamedTuple):
    """Every resolved round's scored targets, and how many targets each round holds."""

    targets: dict[int, list[_ScoredTarget]]
    targets_per_round: int


class BayMatchMetric(Metric):
    """The share of resolved rounds, or of targets, whose crates ended on one bay."""

    name = "bay_match"

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
        if not any(isinstance(event, MoveABoxRoundResolved) for event in events):
            logger.info("bay_match: no resolved move_a_box rounds in this run; skipping")
            return []
        scored = _scored_rounds(events=events)
        unit = "target"
        if scored.targets_per_round == 1:
            unit = "round"
        per_round = [
            RoundObservation(
                round_number=round_number,
                value=sum(target.matched for target in targets) / scored.targets_per_round,
                note=" | ".join(_target_note(target=target) for target in targets),
            )
            for round_number, targets in sorted(scored.targets.items())
        ]
        delivered = _delivery_flags(scored=scored)
        matches = sum(target.matched for targets in scored.targets.values() for target in targets)
        played = len(scored.targets) * scored.targets_per_round
        summary = f"{matches}/{played} {unit}s matched."
        if scored.targets_per_round > 1:
            full = sum(
                len(targets) == scored.targets_per_round and all(t.matched for t in targets)
                for targets in scored.targets.values()
            )
            summary += f" {full}/{len(scored.targets)} rounds matched every target."
        return [
            Measurement(
                metric_name=self.name,
                score=fmean(observation.value for observation in per_round),
                score_unit=f"share of {unit}s whose crates ended on one bay",
                summary=summary
                + " Delivery: "
                + ", ".join(
                    f"{agent_id} {sum(flags)}/{len(flags)}"
                    for agent_id, flags in sorted(delivered.items())
                ),
                per_round=per_round,
                per_agent=[
                    AgentObservation(
                        agent_id=agent_id,
                        value=fmean(flags),
                        note=f"delivered to a bay in {sum(flags)} of {len(flags)} {unit}s",
                    )
                    for agent_id, flags in sorted(delivered.items())
                ],
            )
        ]


def _scored_rounds(events: list[SimulationEvent]) -> _ScoredRounds:
    """Each resolved round's targets: its target events if it logged any, else the round."""
    targets: dict[int, list[_ScoredTarget]] = {}
    for event in events:
        if isinstance(event, MoveABoxTargetResolved):
            targets.setdefault(event.round_number, []).append(
                _ScoredTarget(matched=event.matched, final_bays=dict(event.final_bays))
            )
    if targets:
        return _ScoredRounds(targets=targets, targets_per_round=_targets_per_round(events=events))
    for event in events:
        if isinstance(event, MoveABoxRoundResolved):
            targets[event.round_number] = [
                _ScoredTarget(matched=event.matched, final_bays=dict(event.final_bays))
            ]
    return _ScoredRounds(targets=targets, targets_per_round=1)


def _targets_per_round(events: list[SimulationEvent]) -> int:
    """The run's ``targets_per_round``, from the config its log opens with."""
    for event in events:
        if isinstance(event, SimulationStarted):
            return int(event.scenario_config["targets_per_round"])
    raise ValueError("bay_match: a run with target events has no simulation_started event")


def _delivery_flags(scored: _ScoredRounds) -> dict[str, list[int]]:
    """Per operator, one flag per crate per target the rounds hold: 1 when it scored a bay.

    A target a round never reached counts as no delivery for every crate.
    """
    delivered: dict[str, list[int]] = {}
    for targets in scored.targets.values():
        for target in targets:
            for crate_id, bay in target.final_bays.items():
                delivered.setdefault(owner_of(crate_id), []).append(int(bay is not None))
        missing = scored.targets_per_round - len(targets)
        for crate_id in targets[0].final_bays:
            delivered.setdefault(owner_of(crate_id), []).extend([0] * missing)
    return delivered


def _target_note(target: _ScoredTarget) -> str:
    """Where each crate of one target ended, as a round's note lists it."""
    return "; ".join(
        f"{crate_id}: {_bay_label(bay=bay)}" for crate_id, bay in sorted(target.final_bays.items())
    )


def _bay_label(bay: int | None) -> str:
    """How a round's note names where a crate ended."""
    if bay is None:
        return "no bay"
    return f"bay {bay}"
